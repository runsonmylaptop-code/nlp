from dotenv import load_dotenv
import os
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd
import typing

load_dotenv()

key = os.getenv("KEY")
endpoint = os.getenv("ENDPOINT")

if not key or not endpoint:
    raise ValueError("Brak key lub endpoint w .env")

client = TextAnalyticsClient(endpoint=endpoint, credential=AzureKeyCredential(key))

df = pd.read_csv("balanced.csv")


def analyze_sentiment_batch(texts):
    # show_opinion_mining=True włącza Opinion Mining (znane też jako Aspect-Based Sentiment)
    #
    # Zwykły analyze_sentiment() mówi tylko: "ten dokument jest pozytywny/negatywny"
    # Opinion Mining idzie głębiej i odpowiada na pytanie:
    # "Co konkretnie jest pozytywne/negatywne i dlaczego?"
    #
    # Dla zdania: "The room was clean but the staff was rude."
    # Zwykły sentiment:  negative (ogólnie)
    # Opinion Mining:
    #   Target: "room"  → sentiment: positive, assessment: "clean"
    #   Target: "staff" → sentiment: negative, assessment: "rude"
    #
    # Struktura wynikowa dla każdego zdania:
    #   sentence.mined_opinions     → lista obiektów MinedOpinion
    #     mined_opinion.target      → obiekt TargetSentiment
    #       .text                   → nazwa aspektu np. "room", "staff", "food"
    #       .sentiment              → "positive" / "negative" / "mixed"
    #       .confidence_scores      → pewność predykcji
    #     mined_opinion.assessments → lista obiektów AssessmentSentiment
    #       .text                   → przymiotnik opisujący aspekt np. "clean", "rude"
    #       .sentiment              → "positive" / "negative"
    #
    # Zastosowania: analiza recenzji produktów, hoteli, restauracji -
    # zamiast wiedzieć "klient niezadowolony" wiesz "klient niezadowolony z obsługi"
    result = client.analyze_sentiment(texts, show_opinion_mining=True)
    return result


batch_size = 10

all_result = []

# df.head(80) - przetwarzamy tylko pierwsze 80 recenzji zamiast wszystkich 1000 (to testów)
for i in range(0, len(df.head(80)), batch_size):
    batch = df["Review"].iloc[i:i + batch_size].tolist()
    result = analyze_sentiment_batch(batch)
    all_result.extend(result)

result_df = pd.DataFrame(all_result)

# Filtrujemy tylko dokumenty bez błędów przed dalszą analizą
# is_error może być True gdy tekst jest zbyt długi lub zawiera niedozwolone znaki
doc_result = [doc for doc in all_result if not doc.is_error]

# Słownik dwupoziomowy agregujący opinie według aspektu i sentymentu
# Struktura: { "room": {"positive": [...], "negative": [...]},
#              "staff": {"positive": [...], "negative": [...]}, ... }
# Dzięki temu mamy pełny obraz każdego aspektu w jednym miejscu
target_opinions: typing.Dict[str, typing.Dict[str, list]] = {}

for document in doc_result:
    # Iterujemy po zdaniach - Opinion Mining działa na poziomie zdania
    # Jeden dokument (recenzja) może mieć wiele zdań
    # np. "Room was clean. Staff was rude." → 2 zdania, 2 różne aspekty
    for sentence in document.sentences:

        # mined_opinions jest puste gdy zdanie nie zawiera żadnego aspektu z oceną
        # np. "I stayed here for 3 nights." - brak aspektu, brak opinii
        if sentence.mined_opinions:
            for mined_opinion in sentence.mined_opinions:
                target = mined_opinion.target

                # Filtrujemy tylko positive i negative
                # Pomijamy "mixed" - np. "The room was clean but small"
                # gdzie jeden aspekt dostaje sprzeczne oceny jednocześnie
                if target.sentiment in ('positive', 'negative'):

                    # setdefault() - jeśli aspekt pojawia się pierwszy raz,
                    # tworzy od razu obie listy (positive i negative)
                    # Kolejne wystąpienia tego samego aspektu używają istniejącego wpisu
                    # Przykład pierwszego wywołania dla "room":
                    #   przed: target_opinions = {}
                    #   po:    target_opinions = {"room": {"positive": [], "negative": []}}
                    target_opinions.setdefault(target.text, {"positive": [], "negative": []})

                    # target.sentiment to już string "positive" lub "negative"
                    # używamy go bezpośrednio jako klucza - nie potrzeba if/elif
                    # Przykład dla zdania "The room was clean":
                    #   target.text      = "room"
                    #   target.sentiment = "positive"
                    #   → dodajemy mined_opinion do target_opinions["room"]["positive"]
                    target_opinions[target.text][target.sentiment].append(mined_opinion)

# Iterujemy po aspektach posortowanych malejąco po łącznej liczbie wzmianek
# x[0] = nazwa aspektu np. "room", "staff", "breakfast"
# x[1] = słownik {"positive": [...], "negative": [...]}
# len(x[1]["positive"]) + len(x[1]["negative"]) = suma wszystkich wzmianek
# Dzięki temu aspekty najczęściej pojawiające się w recenzjach są na górze
# reverse=True - sortowanie malejące (najwięcej wzmianek = pierwsza pozycja)
for target_name, sentiments in sorted(
    target_opinions.items(),
    key=lambda x: len(x[1]["positive"]) + len(x[1]["negative"]),
    reverse=True
):
    # Rozpakowujemy listy opinii dla tego aspektu
    # positive = lista obiektów MinedOpinion gdzie target.sentiment == "positive"
    # negative = lista obiektów MinedOpinion gdzie target.sentiment == "negative"
    positive = sentiments["positive"]
    negative = sentiments["negative"]

    # Nagłówek aspektu
    print(f"\n{target_name.upper()}")

    print("-" * 30)

    # ── Linia pozytywna ───────────────────────────────────────────────────────
    # Sprawdzamy czy lista positive nie jest pusta przed wyświetleniem
    # Nie każdy aspekt musi mieć zarówno pochwały jak i skargi
    # np. "location" może mieć tylko pochwały, "queue" tylko skargi
    if positive:
        # Zagnieżdżone list comprehension zbiera przymiotniki ze wszystkich opinii
        # op = jeden obiekt MinedOpinion (jedna opinia o aspekcie w jednym zdaniu)
        # a  = jeden obiekt AssessmentSentiment (jeden przymiotnik opisujący aspekt)
        # Przykład dla "room" positive:
        #   op1.assessments = ["clean", "spacious"]  ← dwa przymiotniki w jednej opinii
        #   op2.assessments = ["comfortable"]        ← jeden przymiotnik w drugiej opinii
        #   wynik: assessments = ["clean", "spacious", "comfortable"]
        assessments = [a.text for op in positive for a in op.assessments]

        # Format linii: "  + (12) clean, spacious, comfortable"
        #   "+"          - znak plus sygnalizuje pozytywny sentyment
        #   len(positive) - liczba zdań gdzie aspekt był oceniony pozytywnie
        #   ', '.join()  - łączy przymiotniki przecinkami w jeden string
        print(f"  + ({len(positive)}) {', '.join(assessments)}")

    # ── Linia negatywna ───────────────────────────────────────────────────────
    # Analogicznie do pozytywnej - sprawdzamy czy są jakieś skargi
    if negative:
        # Ta sama logika co wyżej - zbieramy przymiotniki negatywne
        # Przykład dla "staff" negative:
        #   op1.assessments = ["rude", "unhelpful"]
        #   op2.assessments = ["slow"]
        #   wynik: assessments = ["rude", "unhelpful", "slow"]
        assessments = [a.text for op in negative for a in op.assessments]

        # Format linii: "  - (3) dirty, noisy, small"
        #   "-"          - znak minus sygnalizuje negatywny sentyment
        #   len(negative) - liczba zdań gdzie aspekt był oceniony negatywnie
        #   ', '.join()  - łączy przymiotniki przecinkami w jeden string
        print(f"  - ({len(negative)}) {', '.join(assessments)}")