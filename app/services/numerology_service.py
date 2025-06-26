# app/services/numerology_service.py
"""
Serviço de numerologia para Sky.AI: cálculos de Life Path, Soul Urge e Expression com validação,
logging e tratamento de diferentes formatos de data e vocais.
"""
import re
import unicodedata
import logging
from datetime import datetime

# Configura logger para este módulo
logger = logging.getLogger(__name__)

# Mapeamento de letras para valores numerológicos (Pitagórico)
LETTER_VALUES = {
    'A': 1, 'J': 1, 'S': 1,
    'B': 2, 'K': 2, 'T': 2,
    'C': 3, 'L': 3, 'U': 3,
    'D': 4, 'M': 4, 'V': 4,
    'E': 5, 'N': 5, 'W': 5,
    'F': 6, 'O': 6, 'X': 6,
    'G': 7, 'P': 7, 'Y': 7,
    'H': 8, 'Q': 8, 'Z': 8,
    'I': 9, 'R': 9
}

# Conjunto de vogais (inclui 'Y' como opcional)
VOWELS = {'A', 'E', 'I', 'O', 'U', 'Y'}

# 🔹 Remove acentos e caracteres especiais do nome
def normalize_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValueError("Full name must be a non-empty string.")
    clean = unicodedata.normalize('NFD', name)
    clean = clean.encode('ascii', 'ignore').decode('utf-8')
    return re.sub(r"[-']", '', clean).strip()

# 🔹 Reduz um número para 1-9 ou mestre (11, 22, 33)
def reduce_number(n: int) -> int:
    logger.debug(f"Reducing number: {n}")
    while n > 9 and n not in {11, 22, 33}:
        n = sum(int(d) for d in str(n))
        logger.debug(f"Intermediate reduction: {n}")
    return n

# 🔹 Normalize e valida data de nascimento, aceita YYYY-MM-DD ou DD/MM/YYYY
def parse_birth_date(birth_date: str) -> str:
    if not birth_date or not isinstance(birth_date, str):
        raise ValueError("Birth date must be a non-empty string.")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(birth_date, fmt).date()
            iso = dt.isoformat()
            logger.debug(f"Parsed birth date '{birth_date}' as ISO '{iso}' using format {fmt}")
            return iso
        except ValueError:
            continue
    raise ValueError(f"Birth date '{birth_date}' is not in a recognized format (YYYY-MM-DD or DD/MM/YYYY).")

# 🔹 Caminho de Vida (data de nascimento)
def calculate_life_path_number(birth_date: str) -> int:
    iso_date = parse_birth_date(birth_date)
    digits = re.sub(r'[^0-9]', '', iso_date)
    total = sum(int(d) for d in digits)
    life_path = reduce_number(total)
    logger.info(f"Life Path Number for {iso_date} = {life_path}")
    return life_path

# 🔹 Número da Alma (vogais)
def calculate_soul_urge_number(full_name: str) -> int:
    name = normalize_name(full_name)
    total = 0
    for char in name.upper():
        if char in VOWELS and char in LETTER_VALUES:
            total += LETTER_VALUES[char]
    soul_urge = reduce_number(total)
    logger.info(f"Soul Urge Number for '{full_name}' = {soul_urge}")
    return soul_urge

# 🔹 Número de Expressão (todas as letras)
def calculate_expression_number(full_name: str) -> int:
    name = normalize_name(full_name)
    total = sum(LETTER_VALUES.get(char, 0) for char in name.upper())
    expression = reduce_number(total)
    logger.info(f"Expression Number for '{full_name}' = {expression}")
    return expression

# 🔹 Função principal
def get_numerology(full_name: str, birth_date: str) -> dict:
    try:
        life_path = calculate_life_path_number(birth_date)
        soul_urge = calculate_soul_urge_number(full_name)
        expression = calculate_expression_number(full_name)
        result = {
            "life_path": life_path,
            "soul_urge": soul_urge,
            "expression": expression
        }
        logger.debug(f"Numerology result: {result}")
        return result
    except Exception as e:
        logger.error(f"[Numerology ERROR] {e}")
        return {
            "error": str(e),
            "life_path": None,
            "soul_urge": None,
            "expression": None
        }
