# Wczytywanie zmiennych środowiskowych z pliku .env
# Dzięki temu klucze API nie są zakodowane na stałe w kodzie (bezpieczeństwo)
from dotenv import load_dotenv
import os

# Klient Azure Language Services do analizy tekstu
from azure.ai.textanalytics import TextAnalyticsClient

# Klasa opakowująca klucz API - wymagana przez Azure SDK
from azure.core.credentials import AzureKeyCredential

# Wczytuje plik .env z bieżącego katalogu i ładuje zmienne do os.environ
load_dotenv()

# Pobiera wartości zmiennych środowiskowych
# os.getenv() zwraca None jeśli zmienna nie istnieje (nie rzuca błędu)
key = os.getenv("KEY")
endpoint = os.getenv("ENDPOINT")

# Walidacja - przerywamy działanie jeśli brakuje konfiguracji
# Lepiej dostać czytelny błąd tu niż tajemniczy błąd połączenia później
if not key or not endpoint:
    raise ValueError("Brak key lub endpoint w .env")

# Tworzymy klienta Azure Language Services
# TextAnalyticsClient obsługuje: wykrywanie języka, sentiment, NER, key phrases i inne
# Samo stworzenie obiektu nie nawiązuje jeszcze połączenia - to tylko konfiguracja
client = TextAnalyticsClient(
    endpoint=endpoint,
    credential=AzureKeyCredential(key)
)

# Lista 10 zdań w różnych językach - wejście do analizy
# Azure przyjmuje do 10 dokumentów w jednym wywołaniu (limit dla S0)
# Każdy element listy traktowany jest jako osobny dokument
# Azure automatycznie nadaje im id: "0", "1", "2"...
texts = [
    "This is a simple sentence in English.",    # angielski
    "To jest zdanie po polsku.",                # polski
    "Este es un texto en español.",             # hiszpański
    "Ceci est une phrase en français.",         # francuski
    "Das ist ein deutscher Satz.",              # niemiecki
    "Questa è una frase in italiano.",          # włoski
    "Dit is een zin in het Nederlands.",        # niderlandzki
    "Это предложение на русском языке.",        # rosyjski
    "これは日本語の文です。",                     # japoński
    "这是一个中文句子。"                          # chiński
]

# Wysyłamy wszystkie teksty do Azure w jednym żądaniu HTTP (batch)
# detect_language() zwraca listę obiektów DetectLanguageResult
# w tej samej kolejności co wejściowa lista texts
result = client.detect_language(texts)

# Iterujemy po wynikach - każdy doc odpowiada jednemu tekstowi wejściowemu
for doc in result:
    print("------")

    # doc.id to indeks dokumentu jako string: "0", "1", "2"...
    print(f"Text id: {doc.id}")

    # primary_language to obiekt DetectedLanguage z trzema polami:
    #   .name - pełna nazwa języka po angielsku (np. "Polish")
    #   .confidence_score - pewność predykcji: 0.0 (niska) do 1.0 (pewna)
    #   .iso6391_name - kod języka wg standardu ISO 639-1 (np. "pl", "en", "ja")
    print(
        f"Language: {doc.primary_language.name} "
        f"({doc.primary_language.confidence_score:.2f}) "  # :.2f = 2 miejsca po przecinku
        f"{doc.primary_language.iso6391_name}"
    )