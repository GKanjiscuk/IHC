import sqlite3
import requests
import os
from google.colab import userdata

API_KEY = userdata.get("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
DB_NAME = "movies.db"

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    print("Configurando o banco de dados...")

    cursor.execute("DROP TABLE IF EXISTS movie_genres;")
    cursor.execute("DROP TABLE IF EXISTS movies;")
    cursor.execute("DROP TABLE IF EXISTS genres;")

    cursor.execute("""
    CREATE TABLE movies (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        overview TEXT,
        release_date TEXT,
        vote_average REAL
    );
    """)

    cursor.execute("""
    CREATE TABLE genres (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );
    """)

    cursor.execute("""
    CREATE TABLE movie_genres (
        movie_id INTEGER,
        genre_id INTEGER,
        PRIMARY KEY (movie_id, genre_id),
        FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE CASCADE,
        FOREIGN KEY (genre_id) REFERENCES genres (id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recommendation_history (
        chat_id INTEGER,
        movie_id INTEGER,
        PRIMARY KEY (chat_id, movie_id),
        FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()
    print("Banco de dados pronto.")

def fetch_and_store_genres():
    print("Buscando gêneros em Inglês (para bater com a lógica do bot)...")
    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/genre/movie/list",
            params={"api_key": API_KEY, "language": "en-US"}
        )
        response.raise_for_status()
        genres = response.json().get('genres', [])

        if not genres:
            print("Nenhum gênero encontrado.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for genre in genres:
            cursor.execute(
                "INSERT OR IGNORE INTO genres (id, name) VALUES (?, ?)",
                (genre['id'], genre['name'])
            )

        conn.commit()
        conn.close()
        print(f"Gêneros armazenados: {len(genres)}")

    except requests.RequestException as e:
        print(f"Erro ao buscar gêneros: {e}")

def fetch_and_store_movies(pages_to_fetch=50):
    print(f"Buscando {pages_to_fetch} páginas de filmes populares...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    movies_added = 0

    for page in range(1, pages_to_fetch + 1):
        try:
            response = requests.get(
                f"{TMDB_BASE_URL}/discover/movie",
                params={
                    "api_key": API_KEY,
                    "language": "pt-BR",
                    "sort_by": "popularity.desc",
                    "page": page,
                    "vote_count.gte": 100
                }
            )
            response.raise_for_status()
            movies = response.json().get('results', [])

            if not movies:
                print(f"Sem mais filmes na página {page}.")
                break

            for movie in movies:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO movies (id, title, overview, release_date, vote_average)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        movie['id'],
                        movie['title'],
                        movie.get('overview', ''),
                        movie.get('release_date', ''),
                        movie.get('vote_average', 0)
                    )
                )
                movie_id = movie['id']
                genre_ids = movie.get('genre_ids', [])

                for genre_id in genre_ids:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO movie_genres (movie_id, genre_id)
                        VALUES (?, ?)
                        """,
                        (movie_id, genre_id)
                    )
                movies_added += 1

            print(f"Página {page} processada.")

        except requests.RequestException as e:
            print(f"Erro ao buscar filmes na página {page}: {e}")
            break

    conn.commit()
    conn.close()
    print(f"Processo concluído. Total de {movies_added} registros de filmes processados.")

if __name__ == "__main__":
    if "SUA_NOVA_API_KEY_DO_TMDB" in API_KEY:
        print("ERRO: Por favor, adicione sua NOVA API Key do TMDB ao script 'populate_db.py'.")
    else:
        setup_database()
        fetch_and_store_genres()
        fetch_and_store_movies(pages_to_fetch=50)
        print("\nArquivo 'movies.db' criado com sucesso!")