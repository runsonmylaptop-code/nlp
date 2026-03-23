from dotenv import load_dotenv
import os
from azure.core.credentials import AzureKeyCredential

# ConversationAnalysisClient - klient do odpytywania wdrożonego modelu CLU
# To klient "od frontu" - używany przez aplikację gdy użytkownik coś napisze
from azure.ai.language.conversations import ConversationAnalysisClient

load_dotenv()

key      = os.getenv("KEY")
endpoint = os.getenv("ENDPOINT")

if not key or not endpoint:
    raise ValueError("Brak key lub endpoint w .env")

# Tworzymy klienta do odpytywania modelu CLU
client = ConversationAnalysisClient(endpoint, AzureKeyCredential(key))

# Nazwa projektu CLU zdefiniowana podczas tworzenia w Azure Language Studio
project_name = "helpdesk"

# Nazwa deploymentu - wskazuje konkretną wdrożoną wersję modelu
# Jeden projekt może mieć wiele deploymentów np. "production", "staging", "v2"
# Aplikacja zawsze odpytuje deployment, nie projekt bezpośrednio
deploy_model_name = "helpdesk"

# Zdanie od użytkownika do analizy
# CLU wykryje intencję (co user chce zrobić) i encje (szczegółowe informacje)
# np. intencja: "resetPassword", encja: email="email", urgency="urgent"
query = "My email is not working, I need an urgent password reset"

# Wysyłamy zdanie do Azure CLU - jedno żądanie HTTP
result = client.analyze_conversation(
    body={
        # kind: "Conversation" - typ zadania, dla CLU zawsze taka wartość
        "kind": "Conversation",
        "analysisInput": {
            "conversationItem": {
                # participantId - identyfikator uczestnika konwersacji
                # przydatny przy konwersacjach wieloosobowych, tu nieistotny
                "participantId": "1",

                # id - identyfikator tej konkretnej wiadomości w konwersacji
                # pozwala śledzić kolejność wiadomości w dialogu wieloturowym
                "id": "1",

                # modality - tryb wprowadzania: "text" (pisany) lub "transcript" (mowa)
                "modality": "text",

                # language - kod języka wejściowego wg ISO 639-1
                # model musi być wytrenowany na tym języku lub mieć włączony multilingual
                "language": "en",

                # text - właściwe zdanie użytkownika do analizy
                "text": query
            },
        },
        "parameters": {
            "projectName":    project_name,
            "deploymentName": deploy_model_name,

            # verbose: True - zwraca rozszerzone wyniki:
            # wszystkie intencje z wynikami pewności (nie tylko topIntent)
            # oraz dodatkowe metadane encji
            # verbose: False (domyślnie) - zwraca tylko topIntent i encje
            "verbose": True
        }
    }
)

# ── Wyciągamy wyniki z odpowiedzi ─────────────────────────────────────────────

# topIntent - nazwa intencji z najwyższym wynikiem pewności
# To jest główny wynik CLU - co użytkownik chce zrobić
top_intent = result["result"]["prediction"]["topIntent"]

# entities - lista wszystkich wykrytych encji w zdaniu
# Każda encja to słownik z: category, text, offset, length, confidenceScore
entities = result["result"]["prediction"]["entities"]

# ── Wyświetlamy wyniki ────────────────────────────────────────────────────────

print("view top intent:")

# topIntent to string z nazwą najlepiej dopasowanej intencji np. "resetPassword"
print("\ttop intent: {}".format(result["result"]["prediction"]["topIntent"]))

# intents[0] - pierwsza intencja na liście (ta z najwyższym confidence)
# lista intents jest posortowana malejąco po confidenceScore
# category to nazwa intencji - identyczna jak topIntent dla intents[0]
print("\tcategory: {}".format(result["result"]["prediction"]["intents"][0]["category"]))

# confidenceScore - pewność modelu: 0.0 (brak pewności) do 1.0 (pełna pewność)
# wartości poniżej progu ustawionego w projekcie (np. 0.7) zwracają intencję None
print("\tconfidence score: {}\n".format(result["result"]["prediction"]["intents"][0]["confidenceScore"]))

print("view entities:")
for entity in entities:
    # category - typ encji zdefiniowany w projekcie CLU np. "ProblemType", "Urgency"
    print("\tcategory: {}".format(entity["category"]))

    # text - dosłowny fragment zdania rozpoznany jako encja
    # np. dla encji DeviceType text może być  "printer", "keybord"
    print("\ttext: {}".format(entity["text"]))

    # confidenceScore - pewność że ten fragment to właśnie ta encja
    print("\tconfidence score: {}".format(entity["confidenceScore"]))

# query - oryginalne zdanie użytkownika zwrócone przez Azure dla potwierdzenia
print("query: {}".format(result["result"]["query"]))

# ── Logika biznesowa na podstawie wykrytej intencji ───────────────────────────
# Tu zaczyna się właściwa aplikacja - CLU zwrócił intencję, teraz reagujemy
# Warunek sprawdza czy topIntent to "resetPassword"
if top_intent  == 'resetPassword':
    print("Tak już admin wiem i zmieni Ci hasło")
    # Tu wywołałbyś właściwą akcję biznesową np.:
    # change_password(email=entity["text"], user=user.login)
    # send_reset_email(user_email)
    # create_ticket(priority="urgent", type="password_reset")