from dotenv import load_dotenv
import os
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

key = os.getenv("KEY")
endpoint = os.getenv("ENDPOINT")

if not key or not endpoint:
    raise ValueError("Brak key lub endpoint w .env")

client = TextAnalyticsClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# Pięć tekstów w różnych językach na różne tematy
# Azure automatycznie wykrywa język każdego dokumentu przed analizą
texts = [
    # Polski — programowanie
    "Python jest popularnym językiem programowania, używanym do analizy danych, tworzenia stron internetowych i automatyzacji zadań.",

    # Angielski — machine learning
    "Machine learning allows computers to learn from data and make predictions without being explicitly programmed.",

    # Hiszpański — AI
    "La inteligencia artificial está transformando la industria, mejorando la eficiencia y la toma de decisiones.",

    # Francuski — środowisko
    "Le développement durable est essentiel pour protéger l'environnement et assurer un avenir meilleur.",

    # Niemiecki — energia słoneczna
    "Die Solarenergie ist eine saubere und erneuerbare Energiequelle, die die Abhängigkeit von fossilen Brennstoffen reduziert."
]


# ── ANALIZA 1: Wyodrębnianie kluczowych fraz ─────────────────────────────────
# extract_key_phrases() wysyła wszystkie dokumenty w jednym żądaniu batch
# Zwraca listę obiektów ExtractKeyPhrasesResult w tej samej kolejności co texts
# Algorytm statystyczno-językowy identyfikuje rzeczowniki i grupy nominalne
# które niosą największy ładunek informacyjny w tekście
result = client.extract_key_phrases(texts)

for doc in result:
    print("------")
    print(f"Text id: {doc.id}")

    # doc.key_phrases to lista stringów np. ["Python", "analizy danych", "automatyzacji zadań"]
    # join() łączy je przecinkami w jeden string do wyświetlenia
    print(f"Key phrases: {(',').join(doc.key_phrases)}")


# ── ANALIZA 2: Linkowanie encji do Wikipedii ──────────────────────────────────
# recognize_linked_entities() wykrywa encje i łączy je z artykułami Wikipedii
# Różnica vs NER: NER mówi "to jest Organizacja", linked entities mówi
# "to jest konkretnie Microsoft z id Q2283 na Wikidata"
# Rozwiązuje wieloznaczność: "Python" w kontekście IT → język programowania,
# nie wąż. Azure wybiera właściwy artykuł na podstawie kontekstu zdania
result = client.recognize_linked_entities(texts)

for doc in result:
    print(f"Text id: {doc.id}")
    for linked_entity in doc.entities:
        print("------")

        # linked_entity.name  — ujednolicona nazwa encji (z Wikipedii)
        # linked_entity.url   — bezpośredni link do artykułu Wikipedii
        # Dostępne też: linked_entity.data_source ("Wikipedia"),
        #               linked_entity.data_source_entity_id (id Wikidata)
        print(f"Linked entity: {linked_entity.name} {linked_entity.url}")