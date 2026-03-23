"""
CLU - Airline Bot pipeline
=======================================================================
Packages: azure-ai-language-conversations-authoring==1.0.0b4
          azure-ai-language-conversations==2.0.0b2

pip install azure-ai-language-conversations-authoring azure-ai-language-conversations
"""
from dotenv import load_dotenv
import os
import time
from azure.core.credentials import AzureKeyCredential

# ConversationAuthoringClient - klient do ZARZĄDZANIA projektem CLU
# Używany tylko przez developera: tworzenie projektu, import danych, trening, deployment
# Użytkownik końcowy nigdy nie korzysta z tego klienta
from azure.ai.language.conversations.authoring import ConversationAuthoringClient

# Modele danych wymagane przez SDK w wersji 1.0.0b4
# Ta wersja SDK nie akceptuje zwykłych słowników Python - wymagane są te klasy
from azure.ai.language.conversations.authoring.models import (
    ConversationExportedIntent,       # reprezentuje jedną intencję projektu
    ConversationExportedEntity,       # reprezentuje jedną encję projektu
    ConversationExportedUtterance,    # reprezentuje jedno zdanie treningowe
    ExportedUtteranceEntityLabel,     # etykieta encji w zdaniu: offset + length + category
    ConversationExportedProjectAsset, # kontener łączący intencje + encje + utterances
    CreateProjectOptions,             # ustawienia projektu: język, nazwa, opis
    ProjectKind,                      # enum określający typ projektu (CONVERSATION)
    ProjectSettings,                  # dodatkowe ustawienia np. confidenceThreshold
    ExportedProject,                  # główny obiekt wysyłany do Azure podczas importu
)

# ConversationAnalysisClient - klient do ODPYTYWANIA wdrożonego modelu
# Używany przez aplikację produkcyjną gdy użytkownik zadaje pytanie
from azure.ai.language.conversations import ConversationAnalysisClient

# ── Configuration ──────────────────────────────────────────────────────────────
# Wczytuje klucz i endpoint z pliku .env
load_dotenv()

KEY      = os.getenv("KEY")
ENDPOINT = os.getenv("ENDPOINT")

# Stałe projektu - używane w wielu miejscach kodu
# PROJECT    - nazwa projektu w Azure Language Studio
# MODEL      - etykieta wytrenowanego modelu (można mieć model-v1, model-v2...)
# DEPLOYMENT - nazwa punktu końcowego API (aplikacja zawsze odpytuje "production")
PROJECT    = "AirlineBot"
MODEL      = "model-v1"
DEPLOYMENT = "production"


# ── Helper: automatic offset calculation ──────────────────────────────────────
def entity_label(text: str, phrase: str, category: str) -> ExportedUtteranceEntityLabel:
    """
    Tworzy etykietę encji z automatycznym wyliczeniem offset i length.

    Azure wymaga podania dokładnej pozycji encji w zdaniu:
      offset - indeks pierwszego znaku frazy (licząc od 0)
      length - liczba znaków frazy

    Przykład: text="fly from London to Paris", phrase="London"
      str.find("London") zwraca 9  → offset=9
      len("London") zwraca 6       → length=6

    Rzuca ValueError jeśli fraza nie istnieje w tekście -
    lepiej dostać czytelny błąd tu niż tajemniczy błąd HTTP od Azure.
    """
    offset = text.find(phrase)
    if offset == -1:
        raise ValueError(f"Could not find '{phrase}' in: '{text}'")
    return ExportedUtteranceEntityLabel(
        category=category,
        offset=offset,
        length=len(phrase),
    )


# ── Clients ────────────────────────────────────────────────────────────────────
# AzureKeyCredential opakowuje klucz API w obiekt wymagany przez SDK
# Samo stworzenie klientów nie nawiązuje jeszcze połączenia z Azure
credential  = AzureKeyCredential(KEY)
auth_client = ConversationAuthoringClient(ENDPOINT, credential)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 - create project
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 55)
print("Step 1 - create project")
print("=" * 55)

# Pobieramy listę istniejących projektów i wyciągamy tylko ich nazwy
# Dzięki temu możemy sprawdzić czy projekt już istnieje przed próbą tworzenia
existing = [p["projectName"] for p in auth_client.list_projects()]

# Idempotentne tworzenie - nie wywala się jeśli projekt już istnieje
# Ważne przy wielokrotnym uruchamianiu skryptu 
if PROJECT in existing:
    print(f"  Project '{PROJECT}' already exists - skipping")
else:
    auth_client.create_project(
        PROJECT,
        {
            "projectName":  PROJECT,
            "projectKind":  "Conversation",  # typ projektu - CLU
            "language":     "en",            # główny język projektu
            "multilingual": False,           # tylko angielski, bez wielojęzyczności
            "description":  "Airline bot - flights, baggage, check-in, cancellations",
            # confidenceThreshold: 0.7 - jeśli model nie jest w 70% pewny
            # żadnej intencji, zwróci None zamiast zgadywać
            "settings":     {"confidenceThreshold": 0.7},
        },
    )
    print(f"  Project '{PROJECT}' created")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 - schema: intents, entities, utterances
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("Step 2 - import schema with training data")
print("=" * 55)

# ── Intents ───────────────────────────────────────────────────────────────────
# Intencja = co użytkownik chce zrobić
# Każda intencja odpowiada jednej akcji którą aplikacja potrafi wykonać
# SearchFlight      - szukanie dostępnych lotów na danej trasie
# CheckFlightStatus - sprawdzanie czy lot jest opóźniony lub odwołany
# CheckIn           - odprawa online przed lotem
# BaggageInfo       - pytania o limity i opłaty za bagaż
# CancelFlight      - anulowanie zakupionego biletu
# None              - OBOWIĄZKOWA: zdania spoza domeny bota (pogoda, żarty itp.)
#                     bez niej model próbuje każde zdanie przypisać do jakiejś intencji
intents = [
    ConversationExportedIntent(category="SearchFlight"),
    ConversationExportedIntent(category="CheckFlightStatus"),
    ConversationExportedIntent(category="CheckIn"),
    ConversationExportedIntent(category="BaggageInfo"),
    ConversationExportedIntent(category="CancelFlight"),
    ConversationExportedIntent(category="None"),
]

# ── Entities ──────────────────────────────────────────────────────────────────
# Encja = konkretna informacja wyciągnięta ze zdania użytkownika
# Wszystkie encje są typu "learned" - model uczy się ich z oznaczonych przykładów
# Origin         - miasto/lotnisko wylotu np. "Warsaw", "New York"
# Destination    - miasto/lotnisko przylotu np. "London", "Tokyo"
# Date           - data podróży np. "Friday", "next Monday", "tomorrow"
# FlightNumber   - kod konkretnego lotu np. "AA123", "LH456"
# PassengerCount - liczba pasażerów np. "2", "3"
entities = [
    ConversationExportedEntity(category="Origin"),
    ConversationExportedEntity(category="Destination"),
    ConversationExportedEntity(category="Date"),
    ConversationExportedEntity(category="FlightNumber"),
    ConversationExportedEntity(category="PassengerCount"),
]

# ── Utterance texts as variables ──────────────────────────────────────────────
# Każde zdanie zapisane jako zmienna - kluczowa praktyka!
# Funkcja entity_label() musi otrzymać DOKŁADNIE ten sam tekst co ConversationExportedUtterance
# Gdyby tekst był wpisany dwa razy ręcznie, literówka w jednym miejscu da błędny offset
# Zmienne sf1-sf10 = SearchFlight, cs1-cs8 = CheckFlightStatus itd.

# SearchFlight - 10 zdań treningowych z różnymi trasami i datami
sf1  = "I want to fly from New York to London on Friday"
sf2  = "Find me a flight from Paris to Tokyo next Monday"
sf3  = "Are there any flights from Chicago to Miami tomorrow"
sf4  = "Book a flight from Berlin to Barcelona for 2 passengers"
sf5  = "I need a one way ticket from Los Angeles to New York on Saturday"
sf6  = "Search for flights from Amsterdam to Rome on Sunday"
sf7  = "What flights are available from Dubai to Singapore next week"
sf8  = "I want to travel from Boston to Seattle for 3 passengers"
sf9  = "Show me flights from Madrid to London on Wednesday"
sf10 = "Can I get a flight from Toronto to Vancouver on Thursday"

# CheckFlightStatus - 8 zdań z różnymi numerami lotów i sformułowaniami
cs1  = "What is the status of flight AA123"
cs2  = "Is flight LH456 on time"
cs3  = "Has flight BA789 been delayed"
cs4  = "Check the status of my flight UA321"
cs5  = "Is flight EK202 departing on schedule"
cs6  = "Tell me about flight DL100 today"
cs7  = "Has flight QR505 landed yet"
cs8  = "What time does flight TK001 arrive"

# CheckIn - 7 zdań, część z numerem lotu, część z miastem docelowym
ci1  = "I want to check in for my flight"
ci2  = "How do I check in online for flight AA123"
ci3  = "Can I check in now for my flight to London"
ci4  = "I need to complete online check in for BA456"
ci5  = "Check me in for my flight to Paris"
ci6  = "When does online check in open for my flight"
ci7  = "I want to select my seat for flight LH789"

# BaggageInfo - 8 zdań, wszystkie bez encji (pytania ogólne o bagaż)
bi1  = "How many bags can I bring on the flight"
bi2  = "What is the baggage allowance for economy class"
bi3  = "How much does extra baggage cost"
bi4  = "Can I bring a carry on bag"
bi5  = "What are the luggage restrictions for international flights"
bi6  = "How heavy can my checked bag be"
bi7  = "Is there a fee for a second checked bag"
bi8  = "What size is allowed for cabin baggage"

# CancelFlight - 7 zdań z różnymi sformułowaniami anulowania
cn1  = "I need to cancel my flight"
cn2  = "Cancel my booking for flight AA123"
cn3  = "I want to cancel my trip to London"
cn4  = "Please cancel my reservation for Friday"
cn5  = "How do I cancel my flight and get a refund"
cn6  = "I would like to cancel flight LH456"
cn7  = "Cancel my flight from New York to Paris"

# ── Utterances ────────────────────────────────────────────────────────────────
# Lista wszystkich zdań treningowych i testowych
# Każde utterance musi mieć:
#   text     - zdanie (tu używamy zmiennych sf1, cs1 itp.)
#   intent   - nazwa intencji (musi dokładnie pasować do listy intents powyżej)
#   dataset  - "Train" (80%) lub "Test" (20%)
#   entities - lista etykiet encji obliczona przez entity_label()
#              pusta lista [] gdy zdanie nie zawiera żadnych encji
utterances = [

    # ── SearchFlight (Train) ──────────────────────────────────────────────────
    # sf7 nie ma encji Date bo "next week" jest zbyt niespecyficzne
    # sf1-sf6, sf8-sf10 mają Origin + Destination, część też Date lub PassengerCount
    ConversationExportedUtterance(
        text=sf1, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf1, "New York", "Origin"),
            entity_label(sf1, "London",   "Destination"),
            entity_label(sf1, "Friday",   "Date"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf2, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf2, "Paris",  "Origin"),
            entity_label(sf2, "Tokyo",  "Destination"),
            entity_label(sf2, "Monday", "Date"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf3, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf3, "Chicago",  "Origin"),
            entity_label(sf3, "Miami",    "Destination"),
            entity_label(sf3, "tomorrow", "Date"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf4, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf4, "Berlin",    "Origin"),
            entity_label(sf4, "Barcelona", "Destination"),
            entity_label(sf4, "2",         "PassengerCount"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf5, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf5, "Los Angeles", "Origin"),
            entity_label(sf5, "New York",    "Destination"),
            entity_label(sf5, "Saturday",    "Date"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf6, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf6, "Amsterdam", "Origin"),
            entity_label(sf6, "Rome",      "Destination"),
            entity_label(sf6, "Sunday",    "Date"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf7, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf7, "Dubai",     "Origin"),
            entity_label(sf7, "Singapore", "Destination"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf8, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf8, "Boston",  "Origin"),
            entity_label(sf8, "Seattle", "Destination"),
            entity_label(sf8, "3",       "PassengerCount"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf9, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf9, "Madrid",    "Origin"),
            entity_label(sf9, "London",    "Destination"),
            entity_label(sf9, "Wednesday", "Date"),
        ],
    ),
    ConversationExportedUtterance(
        text=sf10, intent="SearchFlight", dataset="Train",
        entities=[
            entity_label(sf10, "Toronto",   "Origin"),
            entity_label(sf10, "Vancouver", "Destination"),
            entity_label(sf10, "Thursday",  "Date"),
        ],
    ),

    # ── CheckFlightStatus (Train) ─────────────────────────────────────────────
    # Każde zdanie zawiera numer lotu - encja FlightNumber
    # Różne sformułowania: "status of", "on time", "delayed", "landed" itp.
    ConversationExportedUtterance(
        text=cs1, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs1, "AA123", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs2, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs2, "LH456", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs3, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs3, "BA789", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs4, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs4, "UA321", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs5, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs5, "EK202", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs6, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs6, "DL100", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs7, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs7, "QR505", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cs8, intent="CheckFlightStatus", dataset="Train",
        entities=[entity_label(cs8, "TK001", "FlightNumber")],
    ),

    # ── CheckIn (Train) ───────────────────────────────────────────────────────
    # ci1 i ci6 nie mają encji - pytania ogólne bez konkretnego lotu
    # pozostałe mają FlightNumber lub Destination
    ConversationExportedUtterance(
        text=ci1, intent="CheckIn", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=ci2, intent="CheckIn", dataset="Train",
        entities=[entity_label(ci2, "AA123", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=ci3, intent="CheckIn", dataset="Train",
        entities=[entity_label(ci3, "London", "Destination")],
    ),
    ConversationExportedUtterance(
        text=ci4, intent="CheckIn", dataset="Train",
        entities=[entity_label(ci4, "BA456", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=ci5, intent="CheckIn", dataset="Train",
        entities=[entity_label(ci5, "Paris", "Destination")],
    ),
    ConversationExportedUtterance(
        text=ci6, intent="CheckIn", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=ci7, intent="CheckIn", dataset="Train",
        entities=[entity_label(ci7, "LH789", "FlightNumber")],
    ),

    # ── BaggageInfo (Train) ───────────────────────────────────────────────────
    # Wszystkie bez encji - pytania ogólne o zasady bagażu
    # Model uczy się rozpoznawać tę intencję tylko po kontekście słów
    ConversationExportedUtterance(
        text=bi1, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi2, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi3, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi4, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi5, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi6, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi7, intent="BaggageInfo", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=bi8, intent="BaggageInfo", dataset="Train", entities=[],
    ),

    # ── CancelFlight (Train) ──────────────────────────────────────────────────
    # cn1 i cn5 bez encji - ogólne pytania o anulowanie
    # pozostałe mają FlightNumber, Destination lub Date
    ConversationExportedUtterance(
        text=cn1, intent="CancelFlight", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=cn2, intent="CancelFlight", dataset="Train",
        entities=[entity_label(cn2, "AA123", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cn3, intent="CancelFlight", dataset="Train",
        entities=[entity_label(cn3, "London", "Destination")],
    ),
    ConversationExportedUtterance(
        text=cn4, intent="CancelFlight", dataset="Train",
        entities=[entity_label(cn4, "Friday", "Date")],
    ),
    ConversationExportedUtterance(
        text=cn5, intent="CancelFlight", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text=cn6, intent="CancelFlight", dataset="Train",
        entities=[entity_label(cn6, "LH456", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text=cn7, intent="CancelFlight", dataset="Train",
        entities=[
            entity_label(cn7, "New York", "Origin"),
            entity_label(cn7, "Paris",    "Destination"),
        ],
    ),

    # ── None - out of domain (Train) ──────────────────────────────────────────
    # Zdania kompletnie spoza domeny lotniczej
    # Im bardziej różnorodne, tym lepiej model odróżnia "nie mój temat"
    # od intencji domeny - bez tej intencji model zgadywałby nawet dla
    # zupełnie niepowiązanych pytań
    ConversationExportedUtterance(
        text="What is the weather like in London?",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="How much does a hotel room cost?",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="What is your name?",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="What time is it in Tokyo?",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="Tell me a joke",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="How do I get a visa for the USA?",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="What currency is used in Japan?",
        intent="None", dataset="Train", entities=[],
    ),
    ConversationExportedUtterance(
        text="Book me a taxi to the airport",
        intent="None", dataset="Train", entities=[],
    ),

    # ── Test set ──────────────────────────────────────────────────────────────
    # Zdania testowe - NIE używane podczas treningu
    # Azure używa ich do obliczenia metryk: Precision, Recall, F1
    # Zasada: minimum 20% danych powinno być w zestawie testowym
    # Tu mamy po 1 zdaniu testowym na intencję (6 łącznie) - w produkcji więcej
    ConversationExportedUtterance(
        text="Find a flight from London to New York on Monday for 2 passengers",
        intent="SearchFlight", dataset="Test",
        entities=[
            entity_label("Find a flight from London to New York on Monday for 2 passengers", "London",   "Origin"),
            entity_label("Find a flight from London to New York on Monday for 2 passengers", "New York", "Destination"),
            entity_label("Find a flight from London to New York on Monday for 2 passengers", "Monday",   "Date"),
            entity_label("Find a flight from London to New York on Monday for 2 passengers", "2",        "PassengerCount"),
        ],
    ),
    ConversationExportedUtterance(
        text="Is flight UA500 delayed?",
        intent="CheckFlightStatus", dataset="Test",
        entities=[entity_label("Is flight UA500 delayed?", "UA500", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text="I need to check in for my flight to Rome",
        intent="CheckIn", dataset="Test",
        entities=[entity_label("I need to check in for my flight to Rome", "Rome", "Destination")],
    ),
    ConversationExportedUtterance(
        text="What is the baggage limit for my flight?",
        intent="BaggageInfo", dataset="Test", entities=[],
    ),
    ConversationExportedUtterance(
        text="I want to cancel flight EK303",
        intent="CancelFlight", dataset="Test",
        entities=[entity_label("I want to cancel flight EK303", "EK303", "FlightNumber")],
    ),
    ConversationExportedUtterance(
        text="What restaurants are near the airport?",
        intent="None", dataset="Test", entities=[],
    ),
]

# ── Build and send ExportedProject ────────────────────────────────────────────
# Pakujemy wszystkie dane w hierarchię obiektów wymaganą przez SDK

# ConversationExportedProjectAsset łączy trzy listy w jeden kontener
# odpowiednik sekcji "assets" w JSON który Azure wysyła/odbiera
asset = ConversationExportedProjectAsset(
    intents=intents,
    entities=entities,
    utterances=utterances,
)

# ExportedProject to główny obiekt importu - zawiera dane (assets) i konfigurację (metadata)
exported_project = ExportedProject(
    assets=asset,
    metadata=CreateProjectOptions(
        project_name=PROJECT,
        project_kind=ProjectKind.CONVERSATION,  # typ projektu - enum zamiast stringa
        language="en",
        multilingual=False,
        description="Airline bot",
        settings=ProjectSettings(confidence_threshold=0.7),
    ),
    # string_index_type="Utf16CodeUnit" - sposób liczenia offsetów znaków
    # UTF-16 oznacza że każdy znak (w tym polskie litery) ma wartość 1
    # Musi być spójne z tym jak liczymy offsety w entity_label()
    string_index_type="Utf16CodeUnit",
    project_file_version="2022-05-01",
)

# get_project_client() zwraca sub-klienta dla konkretnego projektu
project_client = auth_client.get_project_client(PROJECT)

# begin_import() wysyła dane do Azure i zwraca poller (Long Running Operation)
# Azure nie przetwarza importu natychmiast - kolejkuje go
# poller.result() BLOKUJE wykonanie kodu aż Azure skończy import
# Bez .result() trening zacząłby się zanim dane są gotowe
poller = project_client.project.begin_import(
    exported_project,
    exported_project_format="Conversation",
)
poller.result()
print(f"  Import OK - {len(utterances)} utterances, {len(intents)} intents, {len(entities)} entities")


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 - training
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("Step 3 - training model (may take a few minutes)")
print("=" * 55)

# begin_train() uruchamia trening asynchronicznie i zwraca poller
# body zawiera konfigurację treningu:
#   modelLabel            - etykieta nowego modelu (można mieć v1, v2, v3...)
#   trainingMode          - "standard" (2-5 min, szybki) lub "advanced" (10-20 min, lepszy)
train_poller = project_client.project.begin_train(
    body={
        "modelLabel":            MODEL,
        "trainingMode":          "standard",
        "trainingConfigVersion": "2023-05-01",
    }
)

# Pętla monitorująca postęp treningu co 10 sekund
# train_poller.done() zwraca True gdy operacja się skończyła (sukces lub błąd)
# train_poller.status() zwraca aktualny stan: "running", "succeeded", "failed"
while not train_poller.done():
    print(f"  Status: {train_poller.status()}")
    time.sleep(10)

# .result() po pętli - jeśli trening zakończył się błędem, tu zostanie rzucony wyjątek
# Bez tego błąd treningowy byłby zignorowany
train_poller.result()
print(f"  Training complete - model: '{MODEL}'")

# ══════════════════════════════════════════════════════════════════════════════
# Step 4 - ewaluacja
# ══════════════════════════════════════════════════════════════════════════════
# try/except - ewaluacja może być niedostępna jeśli zestaw testowy jest zbyt mały
# lub jeśli trening nie zakończył się sukcesem
try:
    # get_model_evaluation_summary() pobiera metryki dla konkretnego modelu
    # Metryki są liczone na podstawie zestawu "Test" z utterances
    summary      = project_client.trained_model.get_model_evaluation_summary(
        trained_model_label=MODEL
    )
    intents_eval = summary.get("intentsEvaluation", {})

    # Micro F1 - średnia ważona liczbą przykładów, faworyzuje popularne intencje
    # Macro F1 - każda intencja traktowana równo, lepiej pokazuje słabe punkty
    # Oba powinny być > 0.8 dla modelu produkcyjnego
    print(f"  Micro F1: {intents_eval.get('microF1', 0):.2%}")
    print(f"  Macro F1: {intents_eval.get('macroF1', 0):.2%}\n")

    # Wyniki per intencja - pokazują które intencje model rozpoznaje dobrze
    # a które wymagają więcej danych treningowych
    # Precision - ze wszystkich predykcji danej intencji, ile było poprawnych
    # Recall    - ze wszystkich prawdziwych przykładów, ile model znalazł
    # F1        - średnia harmoniczna Precision i Recall (główna miara jakości)
    print(f"  {'Intent':<24} {'Precision':>10} {'Recall':>8} {'F1':>6}")
    print(f"  {'-'*24} {'-'*10} {'-'*8} {'-'*6}")
    for name, m in intents_eval.get("classes", {}).items():
        print(
            f"  {name:<24}"
            f"  {m.get('precision', 0):>8.2f}"
            f"  {m.get('recall', 0):>6.2f}"
            f"  {m.get('f1', 0):>5.2f}"
        )
except Exception as e:
    print(f"  Evaluation not available: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 - deployment
# ══════════════════════════════════════════════════════════════════════════════
# begin_deploy_project() wdraża model pod nazwą deploymentu
# Jeśli deployment "production" już istnieje - podmienia model pod spodem (hot swap)
# Aplikacja produkcyjna odpytuje zawsze "production" i nie musi wiedzieć
# która wersja modelu tam siedzi
deploy_poller = project_client.deployment.begin_deploy_project(
    deployment_name=DEPLOYMENT,
    body={"trainedModelLabel": MODEL}  # wskazuje który model wdrożyć
)
# .result() czeka na zakończenie deploymentu przed przejściem do testów
deploy_poller.result()
print(f"  Model '{MODEL}' deployed as '{DEPLOYMENT}'")


# ══════════════════════════════════════════════════════════════════════════════
# Step 6 - prediction test
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("Step 6 - prediction test")
print("=" * 55)

# ConversationAnalysisClient - klient do odpytywania (runtime)
# Używamy tego samego endpointu i credential co authoring client
query_client = ConversationAnalysisClient(ENDPOINT, credential)

# Zdania testowe - celowo różne od danych treningowych
# Sprawdzają czy model generalizuje (rozumie nowe sformułowania)
# a nie tylko zapamiętał przykłady treningowe
test_sentences = [
    "I need a flight from Warsaw to London next Friday for 2 people",  # SearchFlight
    "What is the status of flight BA112?",                             # CheckFlightStatus
    "I want to check in for my flight to New York",                    # CheckIn
    "How many kilos can I take on the plane?",                         # BaggageInfo
    "Please cancel my flight AA999",                                   # CancelFlight
    "What is the exchange rate for euros?",                            # None (spoza domeny)
]

for text in test_sentences:
    # analyze_conversation() wysyła jedno zdanie do wdrożonego modelu CLU
    # body zawiera zdanie użytkownika i wskazanie projektu/deploymentu
    result = query_client.analyze_conversation(
        body={
            "kind": "Conversation",
            "analysisInput": {
                "conversationItem": {
                    "id":            "1",
                    "participantId": "user",
                    "text":          text,
                    "language":      "en",
                }
            },
            "parameters": {
                "projectName":    PROJECT,
                "deploymentName": DEPLOYMENT,
            },
        }
    )

    # Wyciągamy wyniki z zagnieżdżonej struktury JSON odpowiedzi
    pred           = result["result"]["prediction"]
    intent         = pred["topIntent"]                          # najlepsza intencja
    confidence     = pred["intents"][0]["confidenceScore"]      # pewność predykcji
    entities_found = pred.get("entities", [])                   # wykryte encje (może być [])

    print(f"\n  Text:    '{text}'")
    print(f"  Intent:  {intent} ({confidence:.0%})")   

    # Wypisujemy każdą wykrytą encję z kategorią i dosłownym tekstem ze zdania
    for ent in entities_found:
        print(f"  Entity:  {ent['category']} = '{ent['text']}'")

print("\n" + "=" * 55)
print("Pipeline completed successfully!")
print("=" * 55)