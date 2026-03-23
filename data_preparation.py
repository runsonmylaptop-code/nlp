import pandas as pd

# Wczytanie zbioru danych z recenzjami hoteli z TripAdvisor
# Plik CSV zawiera kolumny: Review (tekst recenzji) i Rating (ocena 1-5)
df = pd.read_csv("tripadvisor_hotel_reviews.csv")

# Podgląd pierwszych 5 wierszy - sprawdzenie struktury danych
print(df.head())

# Sprawdzenie unikalnych wartości ocen - powinno być [1, 2, 3, 4, 5]
print(df["Rating"].unique())

# Liczba recenzji dla każdej oceny (wartości bezwzględne)
print(df["Rating"].value_counts())

# Procentowy udział każdej oceny w całym zbiorze
# normalize=True zwraca proporcje (0.0-1.0), *100 zamienia na procenty
print(df["Rating"].value_counts(normalize=True) * 100)

import matplotlib.pyplot as plt

# Wykres słupkowy rozkładu ocen
# sort_index() sortuje po wartości oceny (1,2,3,4,5) zamiast po liczebności
df["Rating"].value_counts().sort_index().plot(kind="bar")
plt.xlabel("Rating")
plt.ylabel("Count")
plt.title("Ratings")
plt.show()

# Balansowanie zbioru danych - wyrównanie liczby recenzji per ocena
# Problem: zbiory recenzji są zwykle niezbalansowane - ocen 4 i 5 jest
# znacznie więcej niż 1 i 2. Losujemy dokładnie 200 recenzji z każdej grupy ocen
# random_state=42 - ziarno losowości, gwarantuje powtarzalność wyników
balanced_df = df.groupby("Rating").sample(n=200, random_state=42)

# Zapis zbalansowanego zbioru do nowego pliku CSV
# index=False - nie zapisujemy indeksu Pandas jako osobnej kolumny
# encoding="utf-8" - obsługa polskich i innych znaków specjalnych
balanced_df.to_csv("balanced.csv", index=False, encoding="utf-8")