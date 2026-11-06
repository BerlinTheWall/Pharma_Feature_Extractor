"""Prompts of the third version.

They start from the original prompts (code_aug27/pharma_extractor_package/prompts.py).
Changes:
  * the text may be one piece of a longer section, so the model lists what is
    in this piece only;
  * each item is a separate short term (one organism, one drug, one condition),
    because combined items are split at the commas and break apart;
  * serious warnings: one prompt for the boxed warning and one for the
    Warnings and Precautions section when there is no box;
  * liver and kidney: the decision rules now use the whole set of passages,
    in a fixed order of priority;
  * "CONTRAINDICATED" is spelled correctly.
"""

SYS_LIST = "You are a data extraction tool. You output ONLY a comma-separated list of short terms. No other text."
SYS_OPTION = "You output ONLY one of the specified options, exactly as written. No other text."

_COMMON = """
- The text may be only one part of a longer section. List what appears in THIS text only.
- Write each item as a short phrase in ordinary words with spaces (for example "hereditary angioedema", "severe hepatic impairment"). Separate the items with commas, and do not use commas inside an item.
- Use only the text below. Do not add anything from your own knowledge.
- Return ONLY the comma-separated list. No headings, no numbering, no explanations.
- If there is nothing to list, return NONE."""

INDICATIONS = """Act as a clinical data analyst. Extract the Indications of Use from this text of a Health Canada product monograph.

RULES:
- List every disease, condition or infection that the drug is authorized to treat or prevent, including prophylaxis and maintenance uses.
- If a goal of therapy is named (for example "reduce LDL-C", "reduce the risk of myocardial infarction"), list each goal as a separate item.
- For anti-infective drugs, list each infection and each causative organism named in the indications as a separate item.
- Do not include patient ages, doses, or phrases such as "indicated for".""" + _COMMON + """

Text:
{text}
"""

CONTRAINDICATIONS = """Act as a clinical data analyst. Extract the Contraindications from this text of a Health Canada product monograph.

RULES:
- List every disease, condition, patient group, situation or drug (or drug class) for which the drug must not be used.
- Include hypersensitivity to the drug or its ingredients as one item.
- Ignore text that is not part of the contraindications (for example warnings or dosing).""" + _COMMON + """

Text:
{text}
"""

BOX = """Act as a clinical data analyst. This text is the "Serious Warnings and Precautions" box of a Health Canada product monograph.

RULES:
- List each serious risk, outcome, population or required action named in the box (for example "pregnancy", "fetal injury or death", "discontinue when pregnancy detected").
- Keep each item short (one to six words).""" + _COMMON + """

Text:
{text}
"""

WARNINGS_SECTION = """Act as a clinical data analyst. This text is from the "Warnings and Precautions" section of a Health Canada product monograph.

RULES:
- List each warning topic: each risk, adverse outcome, condition, patient population, monitoring requirement or interacting situation that the section warns about.
- Subheadings of the section are often topics (for example "Hepatic impairment", "Rhabdomyolysis", "Pregnancy").
- Keep each item short (one to six words).""" + _COMMON + """

Text:
{text}
"""

ADVERSE = """Extract ONLY the adverse event names from this text of the Adverse Reactions section.

RULES:
- Find ALL adverse event names (medical terms like "dizziness", "headache", "cough", "fatigue", "hypotension").
- Include terms from tables, lists and paragraphs, including post-market reports.
- NO numbers, NO percentages, NO categories or organ-class headings, NO explanations.""" + _COMMON + """

Text:
{text}
"""

INTERACTIONS = """You are a clinical pharmacist. Extract the drugs and drug classes that interact with {drug}, from this text of the Drug Interactions section.

RULES:
- List every drug, drug class, food, herb or substance named as interacting (for example "warfarin", "CYP3A4 inhibitors", "grapefruit juice", "alcohol").
- Include drugs named in tables.
- Do not include {drug} itself, and do not include doses.""" + _COMMON + """

Text:
{text}
"""

LIVER_OPTIONS = [
    "Use with caution in liver impairment",
    "No dose adjustment required for liver impairment",
    "Dose adjustment recommended with liver impairment",
    "Contraindicated in patients with liver impairment",
]
KIDNEY_OPTIONS = [
    "Use with caution in kidney impairment",
    "No dose adjustment required for kidney impairment",
    "Dose adjustment recommended with kidney impairment",
    "Contraindicated in patients with kidney impairment",
]

_ORGAN = """You are a clinical pharmacist. Decide the recommendation for patients with {organ} impairment, from the passages of a Health Canada product monograph below (the Dosage and Administration section, and other passages that mention the {organ}).

Choose ONE option, using the FIRST rule that applies:
1. If the monograph says the drug itself is contraindicated in patients with {organ} impairment or {organ} disease (not only when it is combined with another drug): "{o4}"
2. Else, if it gives a different dose, a dose limit, a longer interval or a dose reduction for {organ} impairment: "{o3}"
3. Else, if it says to use with caution, to monitor, or that exposure is increased, or that use is not recommended or not studied in {organ} impairment: "{o1}"
4. Else (it says no adjustment is needed, or says nothing about the {organ}): "{o2}"

Return ONLY the option text.

Passages:
{{text}}
"""
LIVER = _ORGAN.format(organ="liver", o1=LIVER_OPTIONS[0], o2=LIVER_OPTIONS[1], o3=LIVER_OPTIONS[2], o4=LIVER_OPTIONS[3])
KIDNEY = _ORGAN.format(organ="kidney", o1=KIDNEY_OPTIONS[0], o2=KIDNEY_OPTIONS[1], o3=KIDNEY_OPTIONS[2], o4=KIDNEY_OPTIONS[3])

PREGNANCY_OPTIONS = ["CONTRAINDICATED", "NOT RECOMMENDED", "USE WITH CAUTION", "NO INFORMATION"]
PREGNANCY = """Based on the text below from a Health Canada product monograph, determine the recommendation for use in pregnancy.
Choose ONE of these exact options, using the FIRST that applies:
- "CONTRAINDICATED" (the text explicitly says the drug is contraindicated in pregnancy)
- "NOT RECOMMENDED" (use in pregnancy should be avoided or is not recommended)
- "USE WITH CAUTION" (use only if the benefit outweighs the risk, or with caution)
- "NO INFORMATION" (the text says nothing about pregnancy)

Return ONLY the option.

Text:
{text}
"""

BREASTFEEDING_OPTIONS = ["CONTRAINDICATED", "NOT RECOMMENDED", "USE WITH CAUTION", "CONSIDERED SAFE", "NO INFORMATION"]
BREASTFEEDING = """Based on the text below from a Health Canada product monograph, determine the recommendation for breastfeeding.
Choose ONE of these exact options, using the FIRST that applies:
- "CONTRAINDICATED" (the drug is contraindicated in nursing women, or breastfeeding must be stopped)
- "NOT RECOMMENDED" (breastfeeding is not recommended or should be avoided during treatment)
- "USE WITH CAUTION" (use with caution, or only if the benefit outweighs the risk)
- "CONSIDERED SAFE" (the drug is considered compatible with breastfeeding)
- "NO INFORMATION" (the text says nothing about breastfeeding)

Return ONLY the option.

Text:
{text}
"""
