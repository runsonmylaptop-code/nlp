import os
from dotenv import load_dotenv

# TextTranslationClient - klient do usługi Azure Translator
# To inna usługa niż Azure Language Services
# Wymaga osobnego zasobu w Azure i osobnego klucza
# Pakiet: azure-ai-translation-text
from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

KEY    = os.getenv("TRANSLATOR_KEY")

# Region jest wymagany dla Translator - inaczej niż w Language Services
# Azure Translator to usługa globalna ale requesty muszą trafiać
# do konkretnego regionu geograficznego gdzie zasób został utworzony
# Domyślna wartość "switzerlandnorth" używana gdy zmienna nie istnieje w .env
REGION = os.getenv("AZURE_TRANSLATOR_REGION", "switzerlandnorth")

# Tworzymy klienta Translator
# region jest obowiązkowy - bez niego Azure odrzuci każde żądanie
client = TextTranslationClient(
    credential=AzureKeyCredential(KEY),
    region=REGION,
)

# Pobieramy tekst od użytkownika przez konsolę
text        = input("Podaj tekst do przetłumaczenia: ")

# Kod języka docelowego wg standardu ISO 639-1
# Przykłady: "en" (angielski), "de" (niemiecki), "fr" (francuski),
#            "pl" (polski), "ja" (japoński), "zh-Hans" (chiński uproszczony)
# .strip() usuwa białe znaki na początku i końcu - zabezpieczenie przed literówką
target_lang = input("Podaj język docelowy (kod ISO, np. en, de, fr): ").strip()

# Wysyłamy żądanie tłumaczenia do Azure
# body=[text] - lista tekstów do przetłumaczenia (można podać wiele naraz)
# to_language=[target_lang] - lista języków docelowych (można tłumaczyć na wiele języków jednocześnie)
# Azure automatycznie wykrywa język źródłowy - nie trzeba go podawać
# Jeśli chcesz podać język źródłowy jawnie, dodaj: from_language="pl"
response = client.translate(body=[text], to_language=[target_lang])

# response[0]  - pierwszy (i jedyny) dokument z listy body
# .translations[0] - pierwsze (i jedyne) tłumaczenie z listy to_language
# .text - przetłumaczony tekst
# Gdybyś podał wiele języków docelowych np. to_language=["en", "de", "fr"]
# to response[0].translations miałoby 3 elementy - po jednym na każdy język
print("\nTłumaczenie:", response[0].translations[0].text)