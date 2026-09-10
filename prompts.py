"""All AI prompts used in the extraction process."""

METADATA_EXTRACTION_PROMPT = """
Identify and extract specific product details from the following pharmaceutical monograph text.

STRICT RULES:
1. Look primarily at Page 1 (the title page).
2. BRAND NAME: Identify the primary brand name. STRIP AWAY prefixes (Pr, N, C, Prn), symbols (®, ™), and strengths. Keep dashes if part of the name. Output in ALL CAPS.
3. COMPANY: Identify the manufacturer/sponsor (e.g., Teva Canada Limited). STRIP AWAY addresses and roles like "Prepared by". Return in Title Case. Prioritize the Canadian Sponsor.
4. INITIAL AUTHORIZATION: Extract the date of initial authorization (e.g., yyyy-mm-dd). If not found, write 'No date available'. Make sure to convert to ISO format (yyyy-mm-dd). Do not return dates in text formats.
5. REVISION DATE: Extract the date of the most recent revision (e.g., yyyy-mm-dd). If not found, write 'No date available'. Make sure to convert to ISO format (yyyy-mm-dd). Do not return dates in text formats.
6. INGREDIENTS: Identify the generic/medicinal name (e.g., Enalapril Maleate). STRIP AWAY forms (Tablets), strengths, and standards (USP). Return in Title Case.
7. DOSAGE: Extract only the numerical strengths (e.g., 2.5 mg, 5 mg). STRIP AWAY all other text.

OUTPUT FORMAT: 
Return ONLY the values in the following order, each on a new line, without labels or extra text:
[CLEAN BRAND NAME]
[CLEAN COMPANY NAME]
[DATE OF INITIAL AUTHORIZATION]
[DATE OF REVISION]
[INGREDIENT(S)]
[DOSAGE STRENGTHS]

Text:
{pdf_text}
"""

# Adverse Drug Events Prompt
ADVERSE_EVENTS_EXTRACTION_PROMPT = """
Extract ONLY the adverse event names from this text.

RULES:
- Look ONLY at the Adverse Reactions section text below
- Find ALL adverse event names (medical terms like "dizziness", "headache", "cough", "fatigue", "hypotension")
- Include both common medical terms and specific medical conditions
- Include terms from tables, lists, and paragraphs
- Return ONLY a comma-separated list of the event names
- NO numbers, NO percentages, NO explanations, NO categories
- NO introductory text, NO bullet points, NO formatting
- JUST the event names separated by commas
- Remove duplicates if the same event appears multiple times
- If no events found, return "NO_ADVERSE_EVENTS_FOUND"

Output shape (placeholders, never output these words):
<event name>, <event name>, <event name>

Every event you list MUST appear in the text below. Never invent a plausible
list of adverse events.

Text to analyze:
{adverse_section}
"""

# Drug Interactions Prompt
DRUG_INTERACTIONS_EXTRACTION_PROMPT = """
You are a clinical pharmacist analyzing drug interaction information.

TASK: Extract ALL drug names mentioned in the Drug Interactions section below.

FORMAT (shape only -- these are placeholders, never output these words):
<drug name>, <drug name>, <drug class>, <drug name>

INSTRUCTIONS:
- Identify every drug, medication, or therapeutic class mentioned in the text
- Include both generic and brand names
- Do Not include the drug itself that you are analyzing (e.g., if the monograph is for "Ramipril", do NOT include "Ramipril" in the list)
- Do not just list all the drugs you see - only include those that are mentioned in the context of drug interactions that could affect the drug in question
- Include drug classes (e.g., "CYP3A4 inhibitors", "anticoagulants", "MAOIs")
- Include specific drugs mentioned in tables or lists
- If the drug is mentioned outside of the drug interactions section, do NOT include it
- Remove duplicates - each drug/drug class should appear only once
- Format as a comma-separated list with a space after each comma
- If no drugs are mentioned, return "******"
- Every drug you list MUST appear verbatim in the text below. Never invent a
  plausible list, and never copy the placeholder names from the format line.
- Do NOT include any explanations, bullet points, numbers, or additional text
- Do NOT include the word "and" - use commas only
- Do NOT include dosage information, just the drug names/classes

Return ONLY the comma-separated list. No other text.

Text to analyze:
{interactions_section_text}
"""

# Indication of Use Prompt
INDICATIONS_EXTRACTION_PROMPT = """
Act as a clinical data analyst. Your task is to extract the Indication of Use from the provided pharmaceutical monograph text.

INSTRUCTIONS:
1. Locate Source: Go to the section titled 'INDICATIONS' or 'INDICATIONS AND CLINICAL USE'.
2. Extract Primary Treatments: Identify all diseases, conditions, or infections the drug is authorized to treat.
3. Include Prophylaxis: Identify if the drug is used for prevention (prophylaxis).
4. Include Maintenance: Identify if the drug prevents recurrence of a condition.
5. Just give out the conditions, no extra words or explanations.
6. Refine Output: 
   - List conditions concisely.
   - Include anatomical locations (e.g., 'systemic', 'oropharyngeal').
   - Format as a single, clean, comma-separated list.
   - Do not include introductory text like 'indicated for' or patient ages.
7. If no clear indications are found, return '******'.

CORRECT output shape (placeholders, never output these words):
<condition>, <condition>, <condition>

WRONG output (never do this):
"It appears you've provided a description of the drug. Here's a summary: 1. Dosage..."
Anything containing a sentence, an introduction, a numbered list, or a closing
remark is wrong, even if the medical content is correct. If the text below does
not actually contain an indications section, return '******' rather than
describing what the text does contain.

Text:
{indications_text}
"""

# Warning and Precautions Prompt
WARNINGS_EXTRACTION_PROMPT = """
Act as a clinical data analyst. Your task is to extract only the core topic names from the 'Serious Warnings and Precautions' box.

STRICT EXTRACTION RULES:
1. LOCATE: Find the text between the header "SERIOUS WARNINGS AND PRECAUTIONS BOX" and the next heading.
2. ISOLATE: Ignore all text outside of this specific segment.
3. EXTRACT: Identify the primary subject of the warning (e.g., 'Pregnancy'). 
4. CLEAN: Remove all verbs, full sentences, and descriptive instructions. 
5. FORMAT: Return only the noun(s) separated by commas.
6. NULL: If the section "SERIOUS WARNINGS AND PRECAUTIONS" does not exist, return '********'.
7. Do not include SERIOUS WARNINGS AND PRECAUTIONS BOX in the output. Only return the extracted topics.
NO PROSE. NO INTRO. NO EXTRA WORDS.

Text:
{pdf_text}
"""

# Liver Dose Adjustment Prompt
LIVER_DOSE_EXTRACTION_PROMPT = """
You are a clinical pharmacist analyzing drug dosage information.

TASK: Determine the dose adjustment recommendation for LIVER impairment from the Dosage and Administration section text below.

Look for keywords related to liver function: "hepatic", "liver", "cirrhosis", "ascites", "hepatitis", "jaundice"

You must choose ONE of these four options exactly as written:
1. "Use with caution in liver impairment"
2. "No dose adjustment required for liver impairment"
3. "Dose adjustment recommended with liver impairment"
4. "Contraindicated in patients with liver impairment"

INSTRUCTIONS:
- Analyze the text carefully for any mention of Dosage Adjustment in Hepatic Impairment, liver cirrhosis, ascites, etc.
- If the text explicitly states that the drug is "contraindicated" in patients with liver impairment, return "Contraindicated in patients with liver impairment".
- If the text provides specific dose adjustment tables or instructions based on liver function, return "Dose adjustment recommended with liver impairment".
- If the text says "caution", "cautious", or mentions monitoring, return "Use with caution in liver impairment".
- If the text explicitly states that no dose adjustment is needed, return "No dose adjustment required for liver impairment".
- If there is no mention of liver impairment in the dosage section, return "No dose adjustment required for liver impairment"
- Do not return numbers or any text other than the exact option.
- Return ONLY the exact option text. No additional text, no explanations.

Text to analyze:
{dosage_section_text}
"""

# Kidney Dose Adjustment Prompt
KIDNEY_DOSE_EXTRACTION_PROMPT = """
You are a clinical pharmacist analyzing drug dosage information.

TASK: Determine the dose adjustment recommendation for KIDNEY impairment from the Dosage and Administration section text below.

Look for keywords related to kidney function: "renal", "kidney", "creatinine", "creatinine clearance", "CrCl", "GFR", "glomerular"

You must choose ONE of these four options exactly as written:
1. "Use with caution in kidney impairment"
2. "No dose adjustment required for kidney impairment"
3. "Dose adjustment recommended with kidney impairment"
4. "Contraindicated in patients with kidney impairment"

INSTRUCTIONS:
- Analyze the text carefully for any mention of Dosage Adjustment in Renal Impairment, creatinine clearance, kidney function, etc.
- If the text explicitly states that the drug is "contraindicated" in patients with kidney impairment, return "Contraindicated in patients with kidney impairment".
- If the text provides specific dose adjustment tables or instructions based on kidney function (e.g., based on creatinine clearance), return "Dose adjustment recommended with kidney impairment".
- If the text says "caution", "cautious", or mentions monitoring, return "Use with caution in kidney impairment".
- If the text explicitly states that no dose adjustment is needed, return "No dose adjustment required for kidney impairment".
- If there is no mention of kidney impairment in the dosage section, return "No dose adjustment required for kidney impairment"
- Do not return numbers or any text other than the exact option.
- Return ONLY the exact option text. No additional text, no explanations.

Text to analyze:
{dosage_section_text}
"""

# Pharmacokinetics Summary Prompt
PK_SUMMARY_PROMPT = """
You are a clinical pharmacologist summarizing pharmacokinetic information from a drug monograph.

TASK: Create a comprehensive, well-written paragraph summarizing ALL pharmacokinetic information from the provided text.

INSTRUCTIONS:
- Write a single cohesive paragraph (not bullet points, not structured sections)
- Include all key PK information: absorption (bioavailability, food effects, Tmax), distribution (protein binding, volume of distribution), metabolism (pathways, active metabolites), and elimination (half-life, clearance, excretion routes)
- Include specific numerical values when present (percentages, times, rates)
- If the drug is a prodrug, explain the conversion process
- Mention any special population considerations (elderly, renal impairment, hepatic impairment)
- Be thorough but concise - aim for 150-250 words
- Use proper scientific language while remaining clear
- Do NOT include any section headers
- Write as a single flowing paragraph
- Only use information explicitly stated in the text - do not add information not present

Text to summarize:
{pk_section_text}
"""

# Elimination (Urine and Faeces) Extraction Prompt
ELIMINATION_EXTRACTION_PROMPT = """
Look ONLY at the ELIMINATION section in this text.

For URINE (keywords: urine, renal, urinary, kidney, renal pathway, renal excretion, urinary excretion):
- Say YES if mentioned, then write the percentage
- Say NO if not mentioned

For FAECES (keywords: feces, faeces, fecal, faecal, biliary, bile, stool):
- Say YES if mentioned, then write the percentage  
- Say NO if not mentioned

Output format (exactly this):
Urine elimination: YES (XX%) or NO
Faeces elimination: YES (XX%) or NO

Text:
{pk_section_text}
"""

# Pharmacodynamics Summary Prompt
PD_SUMMARY_PROMPT = """
You are a clinical pharmacologist summarizing pharmacodynamic information from a drug monograph.

TASK: Create a comprehensive, well-written paragraph summarizing ALL pharmacodynamic information from the provided text.

INSTRUCTIONS:
- Write a single cohesive paragraph (not bullet points, not structured sections)
- Include all key PD information: mechanism of action (molecular target, receptor interactions, enzyme inhibition/activation), pharmacodynamic effects (clinical effects, dose-response relationships), onset of action, duration of action
- Include specific numerical values when present (IC50, EC50, binding affinities, time to effect onset, duration)
- If the drug is a prodrug, explain how activation relates to mechanism of action
- Mention any special population considerations for PD effects (age, organ impairment effects on response)
- Be thorough but concise - aim for 150-250 words
- Use proper scientific language while remaining clear
- Do NOT include any section headers
- Write as a single flowing paragraph
- Only use information explicitly stated in the text - do not add information not present

Text to summarize:
{pd_section_text}
"""

# Pregnancy Status Extraction Prompt
PREGNANCY_STATUS_PROMPT = """
Based on the text below, determine the pregnancy recommendation.
Choose ONE of these exact options:
- "CONTRANDICATED"
- "NOT RECOMMENDED" 
- "USE WITH CAUTION"
- "NO INFORMATION"

Text: {pregnancy_text}
"""

# Pregnancy Summary Prompt
PREGNANCY_SUMMARY_PROMPT = """
You are a clinical pharmacist analyzing drug safety information.

TASK: Create a SHORT summary (2-4 sentences) of the pregnancy-related information from the text below.

Focus on including:
1. Whether the drug is contraindicated in pregnancy
2. What trimester(s) are most dangerous
3. Specific fetal/neonatal risks mentioned (e.g., hypotension, renal failure, malformations)
4. What to do if pregnancy occurs during treatment
5. Do not include any extra phrases like "the following summary".
Keep the summary concise and factual. Use clear, professional language.
Do not include any extra words, *, or phrases (e.g., "In summary", "Overall", "Based on the information provided", etc.).

Text to analyze:
{pregnancy_text}
"""

# Breastfeeding Status Extraction Prompt
BREASTFEEDING_STATUS_PROMPT = """
Based on the text below, determine the breastfeeding recommendation.
Choose ONE of these exact options:
- "CONTRANDICATED" (if breastfeeding should absolutely NOT occur)
- "NOT RECOMMENDED" (if generally advised against)
- "USE WITH CAUTION" (if can be used with monitoring)
- "CONSIDERED SAFE" (if generally considered compatible with breastfeeding)
- "NO INFORMATION"

Text: {breastfeeding_text}
"""

# Breastfeeding Summary Prompt
BREASTFEEDING_SUMMARY_PROMPT = """
You are a clinical pharmacist analyzing drug safety information.

TASK: Create a SHORT summary (2-4 sentences) of the breastfeeding-related information from the text below.

Focus on including:
1. Whether the drug is contraindicated during breastfeeding
2. Whether the drug is excreted in human milk
3. Potential effects on the nursing infant (e.g., sedation, gastrointestinal effects, developmental effects)
4. Effects on milk production/supply (if mentioned)
5. Recommendations for breastfeeding women (e.g., discontinue breastfeeding, monitor infant, avoid use)
6. Do not include any extra phrases like "the following summary".

Keep the summary concise and factual. Use clear, professional language.
Do not include any extra words, *, or phrases (e.g., "In summary", "Overall", "Based on the information provided", etc.).

Text to analyze:
{breastfeeding_text}
"""

# Contraindications Extraction Prompt
CONTRAINDICATIONS_EXTRACTION_PROMPT = """
Act as a clinical data analyst. Extract the Contraindications from the provided text.

STRICT RULES:
1. SEARCH: Look for the section titled "CONTRAINDICATIONS".
2. EXTRACT: Identify only the specific diseases, conditions, or patient groups where the drug is forbidden.
3. FORMAT: Return ONLY a comma-separated list of key phrases.
4. RESTRICTION: Do NOT use full sentences. Do NOT include phrases like "is contraindicated in" or "The drug should not be used by".
5. FALLBACK: If the section is not found or empty, return "********".
6. No sentences, no extra words, just the conditions or diseases.

CORRECT output shape (placeholders, never output these words):
<condition>, <patient group>, <condition>

WRONG output (never do this):
"The text you provided is a summary of the contraindications associated with..."
Anything containing a sentence, an introduction, a numbered list, or a closing
remark is wrong, even if the medical content is correct. Do not wrap the list in
quotation marks. If the text below does not actually contain a contraindications
section, return "********" rather than describing what the text does contain.

Text:
{contraindications_text}
"""


# System messages for AI
METADATA_SYSTEM_MESSAGE = "You are a data extraction tool. Output only raw data strings."
ADVERSE_EVENTS_SYSTEM_MESSAGE = "You output ONLY comma-separated lists. No other text."
DRUG_INTERACTIONS_SYSTEM_MESSAGE = "You output ONLY a comma-separated list of drug names taken verbatim from the supplied text. No other text. Never invent drugs and never repeat placeholder names from the prompt."
INDICATIONS_SYSTEM_MESSAGE = "You output ONLY a comma-separated list of conditions taken from the supplied text. No other text. Never write a summary, a sentence or an introduction, and never invent conditions."
WARNINGS_SYSTEM_MESSAGE = "You are a data extraction tool. Output only raw data strings."
LIVER_SYSTEM_MESSAGE = "You output ONLY one of the four specified options. No other text."
KIDNEY_SYSTEM_MESSAGE = "You output ONLY one of the four specified options. No other text."
PK_SYSTEM_MESSAGE = "You output a single comprehensive paragraph summarizing pharmacokinetic data. No bullet points, no section headers, just a flowing paragraph."
ELIMINATION_SYSTEM_MESSAGE = "You only output two lines: Urine elimination: and Faeces elimination: with YES (percentage) or NO. No summaries, no extra text."
PD_SYSTEM_MESSAGE = "You output a single comprehensive paragraph summarizing pharmacodynamic data. No bullet points, no section headers, just a flowing paragraph."
PREGNANCY_SYSTEM_MESSAGE = "You are a clinical pharmacist. Provide short, factual summaries of drug safety information."
BREASTFEEDING_SYSTEM_MESSAGE = "You are a clinical pharmacist. Provide short, factual summaries of drug safety information for breastfeeding."
CONTRAINDICATIONS_SYSTEM_MESSAGE = "You output ONLY a comma-separated list of conditions or patient groups taken from the supplied text. No other text. Never write a summary, a sentence or an introduction, and never invent conditions."


