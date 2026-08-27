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

def damerau_osa_distance(left: str, right: str) -> int: # leven + less penalizing swap based on pos
    rows = len(left) + 1
    columns = len(right) + 1

    matrix = [
        [0 for _ in range(columns)]
        for _ in range(rows)
    ]

    for row in range(rows):
        matrix[row][0] = row

    for column in range(columns):
        matrix[0][column] = column

    for row in range(1, rows):
        for column in range(1, columns):
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

            best_cost = min(
                deletion,
                insertion,
                replacement,
            )

            if (
                row > 1
                and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                transposition = matrix[row - 2][column - 2] + 1
                best_cost = min(best_cost, transposition)

            matrix[row][column] = best_cost

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


def tokenize(text: str) -> set[str]: # js split normalized text using whitespace
    return set(normalize(text).split())

def token_jaccard(left: str, right: str) -> float: # essentially union and intersection operators
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)

    if not left_tokens and not right_tokens:
        return 1.0

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens

    return len(intersection) / len(union)

def token_coverage(canonical: str, listing: str) -> float: # Minimize extra char penalization
    canonical_tokens = tokenize(canonical)
    listing_tokens = tokenize(listing)

    if not canonical_tokens:
        return 1.0 if not listing_tokens else 0.0

    shared_tokens = canonical_tokens & listing_tokens
    return len(shared_tokens) / len(canonical_tokens)

def character_ngrams(text: str, size: int = 3) -> set[str]: # more lax spelling damage scoring (split in 3 char)
    text = normalize(text).replace(" ", "")

    if not text:
        return set()

    if len(text) < size:
        return {text}

    return {
        text[index:index + size]
        for index in range(len(text) - size + 1)
    }

def trigram_dice(left: str, right: str) -> float: # dice coef calculation
    left_grams = character_ngrams(left)
    right_grams = character_ngrams(right)

    if not left_grams and not right_grams:
        return 1.0

    if not left_grams or not right_grams:
        return 0.0

    shared = left_grams & right_grams

    return (
        2 * len(shared)
        / (len(left_grams) + len(right_grams))
    )

def lexical_score(canonical: str, listing: str) -> dict[str, float]: # synthesis scoring function (prelim)
    edit = levenshtein_similarity(canonical, listing)
    jaccard = token_jaccard(canonical, listing)
    coverage = token_coverage(canonical, listing)
    trigrams = trigram_dice(canonical, listing)

    total = (
        0.35 * edit
        + 0.20 * jaccard
        + 0.25 * coverage
        + 0.20 * trigrams
    )

    return {
        "edit_similarity": edit,
        "token_jaccard": jaccard,
        "canonical_coverage": coverage,
        "trigram_dice": trigrams,
        "total": total,
    }

#Test Zone :)

assert levenshtein_distance("gundam", "gundma") == 2
assert damerau_osa_distance("gundam", "gundma") == 1

