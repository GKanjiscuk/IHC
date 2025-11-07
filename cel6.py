import os
import requests
import json
from typing import Optional, List, Dict
from fuzzywuzzy import process
import re
import telebot
import whisper
from google.colab import userdata
import sqlite3

TELEGRAM_TOKEN = userdata.get("TELEGRAM_TOKEN")
OLLAMA_URL = userdata.get("OLLAMA_URL")
OLLAMA_MODEL = userdata.get("OLLAMA_MODEL")
DB_NAME = "movies.db"

ALLOWED_GENRES = [
    "action", "adventure", "animation", "comedy", "crime", "documentary", "drama",
    "family", "fantasy", "history", "horror", "music", "mystery", "romance",
    "science fiction", "tv movie", "thriller", "war", "western"
]
PT_EN = {
    "acao": "action", "ação": "action", "aventura": "adventure", "animacao": "animation",
    "animação": "animation", "comedia": "comedy", "comédia": "comedy", "crime": "crime",
    "documentario": "documentary", "documentário": "documentary", "drama": "drama",
    "familia": "family", "família": "family", "fantasia": "fantasy", "historia": "history",
    "história": "history", "terror": "horror", "musical": "music", "misterio": "mystery",
    "mistério": "mystery", "romance": "romance", "ficcao": "science fiction",
    "ficção": "science fiction", "ficcao científica": "science fiction",
    "sci-fi": "science fiction", "suspense": "thriller", "guerra": "war", "faroeste": "western"
}


def limpar_resposta(texto: str) -> str:
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    return texto.strip()

def find_genre_in_portuguese(user_input: str) -> Optional[str]:
    lower_input = user_input.lower()
    for pt_term, en_genre in PT_EN.items():
        if pt_term in lower_input:
            return en_genre
    return None

def get_genre_with_fuzzy_search(user_input: str) -> Optional[str]:
    best_match = process.extractOne(user_input.lower(), ALLOWED_GENRES)
    if best_match and best_match[1] > 75:
        return best_match[0]
    return None

def get_genre_id_from_tmdb(genre_name: str) -> Optional[int]:
    """Busca o ID do gênero no banco de dados SQLite local."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM genres WHERE LOWER(name) = ?", (genre_name.lower(),))
        result = cursor.fetchone()

        if result:
            return result[0]
        else:
            print(f"[DB] Gênero '{genre_name}' não encontrado no banco local.")
            return None

    except sqlite3.Error as e:
        print(f"[ERRO SQL] Não foi possível buscar gênero: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_movies_from_tmdb(genre_id: int, chat_id: int) -> List[Dict]:
    """Busca filmes do banco de dados local por genre_id, excluindo os já vistos."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
        SELECT m.id, m.title, m.release_date, m.overview
        FROM movies AS m
        JOIN movie_genres AS mg ON m.id = mg.movie_id
        WHERE mg.genre_id = ?
        AND m.id NOT IN (
            SELECT movie_id
            FROM recommendation_history
            WHERE chat_id = ?
        )
        ORDER BY m.vote_average DESC
        LIMIT 20;
        """

        cursor.execute(query, (genre_id, chat_id))
        results = cursor.fetchall()

        movies_list = [dict(row) for row in results]
        return movies_list

    except sqlite3.Error as e:
        print(f"[ERRO SQL] Falha ao buscar filmes: {e}")
        return []
    finally:
        if conn:
            conn.close()

def generate_recommendations_from_data(movies_data: List[Dict]) -> str:
    simplified_movies = [
        {"title": movie.get("title"), "release_year": movie.get("release_date", "----")[:4], "overview": movie.get("overview")}
        for movie in movies_data[:5]
    ]

    prompt = (
        "Seu trabalho é selecionar 3 desses filmes e apresentá-los de forma atraente para o usuário em português.\n"
        "Para cada filme, inclua o título, o ano de lançamento e crie uma sinopse curta e cativante baseada no 'overview'.\n"
        "Não adicione saudações ou conversas.\n"
        f"Dados dos filmes:\n{json.dumps(simplified_movies, indent=2, ensure_ascii=False)}"
    )

    payload = { "model": OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True }

    try:
        full_response = ""
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=300) as r:
            r.raise_for_status()
            for chunk in r.iter_lines():
                if chunk:
                    data = json.loads(chunk.decode('utf-8'))
                    full_response += data.get("message", {}).get("content", "")

        cleaned_response = limpar_resposta(full_response)
        return cleaned_response
    except requests.exceptions.RequestException as e:
        print(f"\n[ERRO] Falha na chamada final ao Ollama: {e}")
        return "Desculpe, tive um problema para contatar a IA. Tente novamente mais tarde."

def get_movie_recommendation(user_input: str, chat_id: int) -> str:
    """
    Recebe a entrada do usuário, processa e retorna as recomendações de filmes.
    """
    if not user_input:
        return "Nenhuma entrada detectada. Por favor, me diga um gênero de filme."

    genre_name = find_genre_in_portuguese(user_input)
    if not genre_name:
        genre_name = get_genre_with_fuzzy_search(user_input)

    if not genre_name:
        return f"Desculpe, não consegui identificar um gênero válido em '{user_input}'."

    genre_id = get_genre_id_from_tmdb(genre_name)
    if not genre_id:
        return f"Não encontrei o gênero '{genre_name}' no banco de dados de filmes."

    movies = get_movies_from_tmdb(genre_id, chat_id)

    if not movies:
        return f"Uau! Parece que você já viu todas as minhas recomendações para '{genre_name}'. 🚀\n\nQue tal tentar outro gênero?"

    recommendations = generate_recommendations_from_data(movies)

    log_movies_as_seen(chat_id, movies[:5])

    return recommendations

def log_movies_as_seen(chat_id: int, movies_to_log: List[Dict]):
    """Registra os filmes recomendados no histórico do usuário."""
    if not movies_to_log:
        return

    data_to_insert = []
    for movie in movies_to_log:
        if 'id' in movie:
            data_to_insert.append((chat_id, movie['id']))

    if not data_to_insert:
        print("[DB] Nenhum ID de filme para logar.")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.executemany(
            "INSERT OR IGNORE INTO recommendation_history (chat_id, movie_id) VALUES (?, ?)",
            data_to_insert
        )
        conn.commit()
        print(f"[DB] Logado {len(data_to_insert)} filmes para o chat_id {chat_id}")

    except sqlite3.Error as e:
        print(f"[ERRO SQL] Falha ao logar histórico: {e}")
    finally:
        if conn:
            conn.close()


print("Carregando modelo Whisper...")
whisper_model = whisper.load_model("tiny")
print("Modelo carregado.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def transcribe_audio_from_url(file_url: str) -> str:
    """Baixa um arquivo de áudio de uma URL e o transcreve."""
    try:
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            with open("temp_voice.oga", "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        result = whisper_model.transcribe("temp_voice.oga", fp16=False)
        return result["text"]
    except Exception as e:
        print(f"Erro na transcrição: {e}")
        return ""

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "🎬 Olá! Sou seu recomendador de filmes pessoal.\n\n"
        "Me diga um gênero de filme que você gosta, por **texto** ou por **mensagem de voz**, "
        "e eu te darei 3 sugestões incríveis!"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_input = message.text
    chat_id = message.chat.id

    bot.send_message(chat_id, "Entendido! Buscando as melhores recomendações para você... 🧠")

    recommendations = get_movie_recommendation(user_input, chat_id)

    bot.send_message(chat_id, recommendations)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    chat_id = message.chat.id

    try:
        bot.send_message(chat_id, "Opa, um áudio! Deixa eu ouvir e transcrever... 🎤")

        file_info = bot.get_file(message.voice.file_id)
        file_url = f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}'
        transcribed_text = transcribe_audio_from_url(file_url)

        if not transcribed_text:
            bot.send_message(chat_id, "Desculpe, não consegui entender o que você disse no áudio. Pode tentar de novo?")
            return

        bot.send_message(chat_id, f"Acho que você disse: \"_{transcribed_text}_\"\n\nAgora, buscando recomendações com base nisso... 🧠", parse_mode="Markdown")

        recommendations = get_movie_recommendation(transcribed_text, chat_id)

        bot.send_message(chat_id, recommendations)

    except Exception as e:
        print(f"Um erro ocorreu ao processar o áudio: {e}")
        bot.send_message(chat_id, "Ops, tive um problema técnico ao processar seu áudio. Tente novamente, por favor.")

if __name__ == "__main__":
    print("Bot de filmes iniciado! Pressione CTRL+C para parar.")
    if not all([TELEGRAM_TOKEN, OLLAMA_URL, OLLAMA_MODEL]):
         print("\n[ERRO FATAL] Uma ou mais chaves/configurações (TELEGRAM, OLLAMA) não foram encontradas!")
    elif not os.path.exists(DB_NAME):
        print(f"\n[ERRO FATAL] Banco de dados '{DB_NAME}' não encontrado!")
        print(f"Você precisa executar o script 'populate_db.py' primeiro.")
    else:
        print(f"Conectado ao banco de dados '{DB_NAME}' com sucesso.")
        bot.infinity_polling()