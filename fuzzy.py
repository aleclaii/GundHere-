#Fuzzy Matching Algorithms (Hybrid)
#Raw name input -> Normalization -> Similarity scores -> Gunpla-specificity -> Concate Scores -> Norm Scores (0, 1)

# Best approach is Damerau-Levenshtein distance with Token Jaccard Similarity due to the nature of listing titles

import re
import unicodedata


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()

    # Make common model-number styles comparable.
    text = re.sub(r"[-_/]+", " ", text)

    # Remove remaining punctuation.
    text = re.sub(r"[^\w\s]", " ", text)

    # Collapse repeated whitespace.
    text = re.sub(r"\s+", " ", text)

    return text.strip()

def levenshtein_distance(left: str, right: str) -> int:
    rows = len(left) + 1
    columns = len(right) + 1

    matrix = [
        [0 for _ in range(columns)]
        for _ in range(rows)
    ]

    # Converting text into an empty string requires deletions.
    for row in range(rows):
        matrix[row][0] = row

    # Converting an empty string into text requires insertions.
    for column in range(columns):
        matrix[0][column] = column

    for row in range(1, rows):
        for column in range(1, columns): #matrix has extr init row and col representing empty strings so matrix pos 1 is string pos 0
            left_character = left[row - 1]
            right_character = right[column - 1]

            replacement_cost = (
                0 if left_character == right_character else 1
            )

            deletion = matrix[row - 1][column] + 1
            insertion = matrix[row][column - 1] + 1
            replacement = (
                matrix[row - 1][column - 1]
                + replacement_cost
            )

            matrix[row][column] = min(
                deletion,
                insertion,
                replacement,
            )

    return matrix[-1][-1]

def levenshtein_similarity(left: str, right: str) -> float:
    left = normalize(left)
    right = normalize(right)

    if not left and not right:
        return 1.0

    longest_length = max(len(left), len(right))

    if longest_length == 0:
        return 1.0

    distance = levenshtein_distance(left, right)
    return 1.0 - (distance / longest_length)


#Test Case

if __name__ == "__main__":
    examples = [
        ("Gundam", "Gundam"),
        ("Gundam", "Gundma"),
        ("Gundam Aerial", "Gundam Arial"),
        ("RG Nu Gundam", "MG Sazabi"),
    ]

    for left, right in examples:
        score = levenshtein_similarity(left, right)
        print(f"{score:.3f}  {left!r} → {right!r}")
