# Structured fields from Health Canada product monographs

This dataset gives 23 fields extracted by a large language model from 1,433
Health Canada product monographs, collected from the Drug Product Database in
January 2026. There is one row per monograph.

**For research only.** The values were extracted automatically and contain
errors. They must not be used for clinical decisions. The monograph itself
remains the reference.

## How the data was made

The fields were extracted with the original version of the pipeline
(https://github.com/BerlinTheWall/Pharma_Feature_Extractor, tag
`paper-original`), using Llama 3.1 8B. The quality of nine of the fields was
measured on 20 annotated monographs, and the results are in the paper
[CITATION PENDING]. In short:

- the adverse events, contraindications, drug interactions and indications
  miss a part of the items listed in the monograph;
- the serious warnings and precautions have a low recall, since this version
  read them from two fixed pages of each monograph;
- the 14 other fields were not evaluated.

A newer version of the pipeline, described in the paper, has a higher recall,
but it was not used for this dataset [UPDATE IF THE CORPUS IS RERUN].

## Files

- `monograph_extractions_release.csv` (UTF-8) and `.xlsx`: the same table.

## Columns

| Column | Content |
|---|---|
| Monograph ID | Name of the source PDF file in lowercase, without the extension |
| Source PDF | Path of the PDF file in our corpus: therapeutic class / generic drug / file |
| Brand Name, Company | From the first page of the monograph |
| Generic Drug, Drug Class | From the organization of the corpus |
| Initial Authorization, Revision Date | Dates from the monograph |
| Ingredients, Dosage, Dosage Numbers, Dosage Metric | Medicinal ingredients and strengths |
| Indication of Use, Contraindications, Serious warning and precautions, Adverse Events, Drug Interactions | Lists of short terms separated by commas |
| Kidney Function Dose Adjustment, Liver Function Dose Adjustment | One of: use with caution, no dose adjustment required, dose adjustment recommended, contraindicated |
| Pregnancy Recommendation, Breastfeeding Recommendation | One of: contraindicated, not recommended, use with caution, considered safe (breastfeeding only), no information |
| Pharmacokinetics, Metabolism, Elimination, Pharmacodynamics | Short summaries |
| Pregnancy Summary, Breastfeeding Summary | Summaries of two to four sentences |
| DIN | Drug Identification Number of this product and strength, when it was verified |
| Monograph PDF (Health Canada) | Link to the monograph on pdf.hres.ca, when it was verified |
| DPD Product Page | Page of the product in the Drug Product Database, when the DIN was verified |
| Note | Warning for the rows that should not be used |

Values such as `section_not_found` or `no breastfeeding information found`
mean that the pipeline did not find the field.

## Links and DINs

The links were first matched automatically, and the match was not always right.
Therefore, we downloaded every linked PDF and compared it with our copy of the
monograph. A link is given only when the PDF is the same file, the same
monograph with a close text (it was revised after January 2026), or a
monograph whose first pages name the same brand and company. A DIN is given
only when, in addition, its strength and its company or brand in the Drug
Product Database match the monograph. 1,261 rows have a link and 1,229 have a
DIN; the others are empty. The scripts are in `paper/release` of the
repository (https://github.com/BerlinTheWall/Pharma_Feature_Extractor/tree/main/paper/release).

## Scanned monographs

Four monographs (LEVOFLOXACIN 500mg and RIVA-METOPROLOL-L 25mg, 50mg and
100mg) are scanned PDF files with almost no text. Most of their list fields
were not taken from the document, and these rows are marked in `Note`. One
other scanned monograph (DILTIAZEM HYDROCHLORIDE INJECTION 5mg/ml) could not
be read and is not in the table.

## License

The data is released under the Creative Commons Attribution 4.0 International
license (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). You may
share and adapt it for any purpose, as long as you cite the paper and this
dataset. The product monographs themselves belong to their manufacturers and
are available from Health Canada; they are not included.
