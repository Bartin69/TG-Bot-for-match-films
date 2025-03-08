# bot.py

import psycopg2
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
import requests
import random
from config import DB_CONFIG, KINOPOISK_API_URL, KINOPOISK_API_KEY, TELEGRAM_BOT_TOKEN

# Подключение к PostgreSQL
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users_tg (
            user_id BIGINT PRIMARY KEY,
            username TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            user_id BIGINT,
            movie_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users_tg(user_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connections (
            user_id BIGINT,
            partner_id BIGINT,
            FOREIGN KEY (user_id) REFERENCES users_tg(user_id),
            FOREIGN KEY (partner_id) REFERENCES users_tg(user_id)
        )
    ''')
    conn.commit()
    conn.close()

# Главное меню
def show_main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🔗 Добавить привязку", callback_data="add_connection")],
        [InlineKeyboardButton("📋 Показать привязки", callback_data="show_connections")],
        [InlineKeyboardButton("❌ Удалить привязку", callback_data="delete_connection")],
        [InlineKeyboardButton("🎬 Показать фильм", callback_data="show_movies")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        update.callback_query.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    else:
        update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# Команда /start
def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    # Добавляем пользователя в базу данных
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users_tg (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING', (user_id, username))
    conn.commit()
    conn.close()

    # Показываем главное меню
    show_main_menu(update, context)

# Обработка кнопки "Показать привязки"
def show_connections(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    # Получаем список привязанных пользователей
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем username привязанных пользователей
    cursor.execute('''
        SELECT u.username 
        FROM connections c
        JOIN users_tg u ON c.partner_id = u.user_id
        WHERE c.user_id = %s
    ''', (user_id,))
    partners = cursor.fetchall()
    conn.close()

    if not partners:
        query.message.reply_text("У вас нет привязок. Сначала добавьте привязку.")
        return

    # Создаем клавиатуру для выбора привязки
    keyboard = [[InlineKeyboardButton(partner[0], callback_data=f"match_{partner[0]}")] for partner in partners]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.message.reply_text("Выберите привязку для поиска мэтчей:", reply_markup=reply_markup)

# Обработка кнопки "Добавить привязку"
def add_connection(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    # Запрашиваем username партнера
    query.message.reply_text("Введите username партнера:")

    # Сохраняем состояние для следующего шага
    context.user_data['action'] = 'add_connection'

# Обработка ввода username партнера
def handle_username(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    partner_username = update.message.text

    # Находим ID партнера
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users_tg WHERE username = %s', (partner_username,))
    partner = cursor.fetchone()

    if partner:
        partner_id = partner[0]
        # Добавляем привязку
        cursor.execute('INSERT INTO connections (user_id, partner_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (user_id, partner_id))
        conn.commit()
        update.message.reply_text(f"Привязка к {partner_username} добавлена!")
    else:
        update.message.reply_text("Пользователь не найден.")

    conn.close()

def delete_connection(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    # Получаем список привязок пользователя
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.username 
        FROM connections c
        JOIN users_tg u ON c.partner_id = u.user_id
        WHERE c.user_id = %s
    ''', (user_id,))
    partners = cursor.fetchall()
    conn.close()

    if not partners:
        query.message.reply_text("У вас нет привязок для удаления.")
        return

    # Создаем клавиатуру для выбора привязки
    keyboard = [[InlineKeyboardButton(partner[0], callback_data=f"delete_{partner[0]}")] for partner in partners]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.message.reply_text("Выберите привязку для удаления:", reply_markup=reply_markup)

def handle_delete_connection(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    partner_username = query.data.split('_')[1]  # Получаем username из callback_data

    # Находим ID партнера по username
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users_tg WHERE username = %s', (partner_username,))
    partner = cursor.fetchone()

    if not partner:
        query.message.reply_text("Пользователь не найден.")
        conn.close()
        return

    partner_id = partner[0]

    # Удаляем привязку
    cursor.execute('DELETE FROM connections WHERE user_id = %s AND partner_id = %s', (user_id, partner_id))
    conn.commit()
    conn.close()

    query.message.reply_text(f"Привязка с {partner_username} удалена!")

# Обработка скипа
def skip_movie(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    show_movies(update, context)  # Показываем следующий фильм

# Модифицированная функция show_movies
# Функция для показа фильма
def show_movies(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    # Сообщение о загрузке
    loading_message = query.message.reply_text("🔄 Идет загрузка информации о фильме...")

    # Задаем фильтры запроса
    params = {
        "order": "RATING",
        "type": "FILM",
        "ratingFrom": 3,
        "ratingTo": 10,
        "yearFrom": 1900,
        "yearTo": 2025,
        "page": random.randint(1, 5)
    }

    # Запрос к API для получения списка фильмов
    response = requests.get(KINOPOISK_API_URL, headers={"X-API-KEY": KINOPOISK_API_KEY}, params=params)

    if response.status_code != 200:
        loading_message.edit_text(f"Ошибка API: {response.status_code}\n{response.text}")
        return

    movies = response.json().get("items", [])
    if not movies:
        loading_message.edit_text("Ошибка: API не вернул список фильмов.")
        return

    # Выбираем случайный фильм
    movie = random.choice(movies)
    movie_id = movie.get("kinopoiskId")

    if not movie_id:
        loading_message.edit_text("Ошибка: Не удалось получить ID фильма.")
        return

    # Запрос к API для получения деталей фильма
    movie_details_url = f"{KINOPOISK_API_URL}/{movie_id}"
    response_details = requests.get(movie_details_url, headers={"X-API-KEY": KINOPOISK_API_KEY})

    if response_details.status_code != 200:
        loading_message.edit_text(f"Ошибка API при запросе деталей фильма: {response_details.status_code}\n{response_details.text}")
        return

    movie_details = response_details.json()

    # Извлекаем данные о фильме
    title = movie_details.get("nameRu", "Без названия")
    description = movie_details.get("description", movie_details.get("shortDescription", "Описание отсутствует"))
    rating = movie_details.get("ratingKinopoisk", "Нет рейтинга")
    year = movie_details.get("year", "Неизвестно")
    poster_url = movie_details.get("posterUrl", "")

    # Жанры и страны
    genres = movie_details.get("genres", [])
    genres_str = ", ".join([genre.get("genre", "Неизвестно") for genre in genres]) if genres else "Жанры не указаны"
    countries = movie_details.get("countries", [])
    countries_str = ", ".join([country.get("country", "Неизвестно") for country in countries]) if countries else "Страны не указаны"

    # Ссылка на фильм
    web_url = movie_details.get("webUrl", "Ссылка отсутствует")

    # Сохраняем ID фильма в контексте пользователя
    context.user_data['current_movie'] = movie_id

    # Создаем кнопки управления
    keyboard = [
        [InlineKeyboardButton("❤️ Лайк", callback_data="like")],
        [InlineKeyboardButton("➡️ Скип", callback_data="skip")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Формируем сообщение
    message_text = (
        f"🎬 Название: {title}\n"
        f"📅 Год: {year}\n"
        f"⭐ Рейтинг: {rating}\n"
        f"🌍 Страны: {countries_str}\n"
        f"🎭 Жанры: {genres_str}\n"
        f"📖 {description}\n"
        f"🔗 [Ссылка на фильм]({web_url})"
    )

    # Удаляем сообщение о загрузке и отправляем информацию о фильме
    loading_message.delete()
    if poster_url:
        query.message.reply_photo(photo=poster_url, caption=message_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        query.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

# Модифицированная функция like_movie
def like_movie(update: Update, context: CallbackContext):
    user_id = update.callback_query.from_user.id
    movie_id = context.user_data.get('current_movie')

    # Добавляем лайк в базу данных
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO likes (user_id, movie_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (user_id, movie_id))
    conn.commit()
    conn.close()

    update.callback_query.answer("Фильм добавлен в лайки!")
    show_movies(update, context)  # Показываем следующий фильм

# Обработка кнопки "Назад"
def back_to_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    show_main_menu(update, context)

# Показ мэтчей
def show_matches(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    partner_username = query.data.split('_')[1]  # Получаем username из callback_data

    # Находим ID партнера по username
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users_tg WHERE username = %s', (partner_username,))
    partner = cursor.fetchone()

    if not partner:
        query.message.reply_text("Пользователь не найден.")
        conn.close()
        return

    partner_id = partner[0]

    # Находим общие лайки
    cursor.execute('''
        SELECT movie_id FROM likes WHERE user_id = %s
        INTERSECT
        SELECT movie_id FROM likes WHERE user_id = %s
    ''', (user_id, partner_id))
    common_movies = cursor.fetchall()
    conn.close()

    if common_movies:
        movie_titles = [movie[0] for movie in common_movies]
        query.message.reply_text(f"Общие фильмы с {partner_username}: {', '.join(map(str, movie_titles))}")
    else:
        query.message.reply_text(f"У вас нет общих фильмов с {partner_username}.")

# Запуск бота
def main():
    init_db()  # Инициализация базы данных

    updater = Updater(TELEGRAM_BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(add_connection, pattern="add_connection"))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_username))
    dp.add_handler(CallbackQueryHandler(show_movies, pattern="show_movies"))
    dp.add_handler(CallbackQueryHandler(like_movie, pattern="like"))
    dp.add_handler(CallbackQueryHandler(skip_movie, pattern="skip"))
    dp.add_handler(CallbackQueryHandler(back_to_menu, pattern="back_to_menu"))
    dp.add_handler(CallbackQueryHandler(show_connections, pattern="show_connections"))
    dp.add_handler(CallbackQueryHandler(delete_connection, pattern="delete_connection"))
    dp.add_handler(CallbackQueryHandler(handle_delete_connection, pattern="delete_*"))
    dp.add_handler(CallbackQueryHandler(show_matches, pattern="match_*"))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()