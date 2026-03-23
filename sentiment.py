from dotenv import load_dotenv
import os
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd

load_dotenv()

key = os.getenv("KEY")
endpoint = os.getenv("ENDPOINT")

if not key or not endpoint:
    raise ValueError("Brak key lub endpoint w .env")

client = TextAnalyticsClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# Wczytanie zbalansowanego zbioru przygotowanego w poprzednim kroku
# 1000 recenzji: po 200 dla każdej oceny 1-5
df = pd.read_csv("balanced.csv")


def analyze_sentiment_batch(texts):
    # Wysyłamy paczkę tekstów do Azure - jeden request HTTP dla całej paczki
    # analyze_sentiment() zwraca listę obiektów AnalyzeSentimentResult
    # w tej samej kolejności co wejściowa lista texts
    response = client.analyze_sentiment(texts)

    result = []

    for doc in response:
        # is_error sprawdzamy zawsze - Azure może odrzucić konkretny dokument
        # (np. zbyt długi tekst, niedozwolone znaki) nie przerywając całego batcha
        if not doc.is_error:
            result.append({
                # Sentyment ogólny: "positive", "negative", "neutral" lub "mixed"
                "Sentiment_from_azure": doc.sentiment,

                # Trzy wyniki pewności - zawsze sumują się do 1.0
                # Model przypisuje każdemu dokumentowi prawdopodobieństwo
                # przynależności do każdej klasy jednocześnie
                "Positive_score": doc.confidence_scores.positive,
                "Neutral_score":  doc.confidence_scores.neutral,
                "Negative_score": doc.confidence_scores.negative
            })
        else:
            # Błąd dla konkretnego dokumentu - zapisujemy None zamiast przerywać pętlę
            # Dzięki temu wyniki mają tę samą długość co wejście (ważne przy concat)
            result.append({
                "Sentiment_from_azure": "Error",
                "Positive_score": None,
                "Neutral_score":  None,
                "Negative_score": None
            })

    return result


# Azure akceptuje maksymalnie 10 dokumentów w jednym wywołaniu analyze_sentiment()
# Dlatego dzielimy 1000 recenzji na paczki po 10 i wysyłamy je po kolei
batch_size = 10

all_result = []

# range(0, 1000, 10) generuje: 0, 10, 20, ..., 990
# Każda iteracja przetwarza wiersze df[i : i+10]
for i in range(0, len(df), batch_size):
    # iloc[i:i+batch_size] - wycinamy 10 wierszy z kolumny Review
    # .tolist() konwertuje Series Pandas na zwykłą listę stringów
    batch = df["Review"].iloc[i:i + batch_size].tolist()
    result = analyze_sentiment_batch(batch)

    # extend() dodaje elementy listy (nie zagnieżdża) - po pętli all_result
    # ma dokładnie 1000 słowników, po jednym na każdą recenzję
    all_result.extend(result)

# Tworzymy DataFrame z wyników Azure (1000 wierszy × 4 kolumny)
result_df = pd.DataFrame(all_result)

# Łączymy oryginalny DataFrame z wynikami Azure kolumna-w-kolumnę (axis=1)
# reset_index(drop=True) - resetujemy indeksy obu DataFrame'ów przed złączeniem,
# żeby Pandas dopasował wiersze po pozycji a nie po indeksie
df = pd.concat([df.reset_index(drop=True), result_df], axis=1)


# Konwersja numerycznej oceny (1-5) na kategorię sentymentu
# Tworzymy "ground truth" - prawdziwy sentyment według oceny recenzenta
# Logika biznesowa: 4-5 = pozytywna, 3 = neutralna, 1-2 = negatywna
def rating_to_sentiment(rating):
    if rating >= 4:
        return "positive"
    elif rating == 3:
        return "neutral"
    else:
        return "negative"


# apply() wywołuje funkcję dla każdego wiersza kolumny Rating
# Wynik trafia do nowej kolumny rating_to_sentiment
df["rating_to_sentiment"] = df["Rating"].apply(rating_to_sentiment)

# Podgląd pierwszych 5 wierszy - porównanie oceny z wynikiem Azure
for idx, row in df.head(5).iterrows():
    print(f"--- Wiersz {idx} ---")
    print(f"Review:               {row['Review']}")
    print(f"Rating:               {row['Rating']}")
    print(f"Sentiment_from_azure: {row['Sentiment_from_azure']}")
    print(f"Positive_score:       {row['Positive_score']}")
    print(f"Neutral_score:        {row['Neutral_score']}")
    print(f"Negative_score:       {row['Negative_score']}")
    print(f"rating_to_sentiment:  {row['rating_to_sentiment']}")


# ── Analiza błędów modelu ─────────────────────────────────────────────────────
# Szukamy przypadków gdzie Azure i recenzent się nie zgadzają
# Przypadek 1: recenzent dał 1-2 (negatywna) ale Azure mówi "positive"
# To tzw. False Positive - model pomylił negatywną recenzję z pozytywną(?) albo użytkownik źle zaznaczył flagę
mistakes = df[
    (df["rating_to_sentiment"] == "negative") &
    (df["Sentiment_from_azure"] == "positive")
]

print(f"Negative → Positive (False Positive): {len(mistakes)}")

# Przypadek 2: recenzent dał 4-5 (pozytywna) ale Azure mówi "negative"
# To tzw. False Negative - model pomylił pozytywną recenzję z negatywną (?) albo błąd użytkownika
mistakes_good_to_bad = df[
    (df["rating_to_sentiment"] == "positive") &
    (df["Sentiment_from_azure"] == "negative")
]
print(f"Positive → Negative (False Negative): {len(mistakes_good_to_bad)}")

# Wyświetlamy wszystkie przypadki gdzie model ocenił pozytywną recenzję jako negatywną
# Analiza tych przypadków pomaga zrozumieć gdzie model się myli
# Typowe przyczyny: ironia, krytyka w pozytywnym kontekście, mieszane opinie
for idx, row in mistakes_good_to_bad.iterrows():
    print(f"--- Wiersz {idx} ---")
    print(f"Review:               {row['Review']}")
    print(f"Rating:               {row['Rating']}")
    print(f"Sentiment_from_azure: {row['Sentiment_from_azure']}")
    print(f"Positive_score:       {row['Positive_score']}")
    print(f"Neutral_score:        {row['Neutral_score']}")
    print(f"Negative_score:       {row['Negative_score']}")
    print(f"rating_to_sentiment:  {row['rating_to_sentiment']}")