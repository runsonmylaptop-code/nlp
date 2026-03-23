from dotenv import load_dotenv
import os

# QuestionAnsweringClient - klient do odpytywania bazy wiedzy QnA w czasie rzeczywistym
# To klient "od frontu" - używany przez aplikację produkcyjną gdy użytkownik zadaje pytanie
from azure.ai.language.questionanswering import QuestionAnsweringClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

key      = os.getenv("KEY")
endpoint = os.getenv("ENDPOINT")

# Tworzymy klienta do odpytywania - samo stworzenie obiektu nie nawiązuje połączenia
client = QuestionAnsweringClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# Nazwa projektu QnA zdefiniowana podczas tworzenia projektu w Azure
project_name = "my-faq"

# Nazwa deploymentu - jeden projekt może mieć wiele deploymentów np. "production", "staging"
# Aplikacja zawsze odpytuje konkretny deployment, nie projekt bezpośrednio
# Dzięki temu można podmienić zawartość bazy wiedzy bez zmiany kodu aplikacji
deploy_name  = "production"

# Pytanie zadane przez użytkownika w języku naturalnym
# QnA nie wymaga dokładnego dopasowania słów - model semantycznie porównuje
# pytanie z wszystkimi parami Q&A w bazie i zwraca najbardziej pasującą odpowiedź
# "What time is check in" zostanie dopasowane nawet jeśli w bazie jest
# "What are the check-in hours?" lub "When can I check into my room?"
question = "What time is check-in"

# Wysyłamy pytanie do Azure - jedno żądanie HTTP
# project_name i deployment_name wskazują konkretną bazę wiedzy do przeszukania
# Domyślnie zwracane są top=1 odpowiedzi - można zwiększyć przez parametr top=3
# Można też ustawić confidence_threshold np. 0.5 żeby odrzucić słabe dopasowania
result = client.get_answers(
    question=question,
    project_name=project_name,
    deployment_name=deploy_name
)

# result.answers to lista obiektów KnowledgeBaseAnswer posortowana malejąco po confidence
# Każdy obiekt reprezentuje jedną parę Q&A z bazy wiedzy dopasowaną do pytania
for answer in result.answers:

    # Pełna odpowiedź tekstowa z bazy wiedzy
    # To jest tekst który wpisałeś jako odpowiedź przy tworzeniu pary Q&A
    print(f"Odpowiedź: {answer.answer}")

    # Krótka odpowiedź wyodrębniona z pełnej odpowiedzi (Extractive QA)
    # Azure zaznacza najważniejszy fragment odpowiedzi jako "short answer"
    # Przydatne gdy pełna odpowiedź jest długa a chcesz pokazać tylko kluczową informację
    # np. pełna: "Check-in starts at 3pm and ends at 10pm." → short: "3pm"
    # Może być None jeśli Extractive QA nie jest włączone lub nie znaleziono fragmentu
    print(f"short_answer: {answer.short_answer}")

    # Wynik pewności dopasowania - liczba od 0.0 do 1.0
    # Im bliżej 1.0 tym model jest bardziej pewny że to właściwa odpowiedź
    # Wartości poniżej 0.5 oznaczają słabe dopasowanie - warto wtedy
    # wyświetlić defaultAnswer zamiast tej odpowiedzi
    print(f"confidence: {answer.confidence}")

    # Dodatkowe właściwości zwrócone przez Azure - słownik z metadanymi
    # Mogą zawierać np. język odpowiedzi, wersję modelu itp.
    # Zwykle pusty słownik {} dla standardowych odpowiedzi
    print(f"additional_properties: {answer.additional_properties}")

    # Lista wszystkich pytań przypisanych do tej pary Q&A w bazie wiedzy
    # Jedna odpowiedź może mieć wiele wariantów pytania np.:
    # ["What time is check-in?", "When can I check in?", "Check-in hours?"]
    # Przydatne do debugowania - możesz sprawdzić z którymi pytaniami model
    # skojarzył tę odpowiedź
    print(f"questions: {answer.questions}")

    # Obiekt dialogu zawierający follow-up prompts - sugerowane kolejne pytania
    # Pozwala budować dialog wieloturowy: po odpowiedzi bot proponuje
    # powiązane pytania które użytkownik może kliknąć
    # answer.dialog.prompts to lista obiektów KnowledgeBaseAnswerPrompt
    # Każdy prompt ma: .display_text (tekst przycisku) i .qna_id (id pary Q&A)
    # Przykład: po odpowiedzi o check-in prompty mogą być:
    # ["What time is check-out?", "Can I store luggage before check-in?"]
    # Może być pusta lista [] jeśli dla tej pary nie zdefiniowano follow-up prompts
    print(f"dialog: {answer.dialog.prompts}.")