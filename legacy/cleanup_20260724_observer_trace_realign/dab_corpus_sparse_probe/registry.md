# DAB Query Corpus Registry

Created at: `2026-07-19T06:32:41.191755+00:00`

DAB root: `external/DataAgentBench_sparse`

## Summary

| Metric | Count |
|---|---:|
| Domains | 17 |
| Query cases | 104 |
| Definition-ready cases | 104 |
| Dataset-materialized cases | 104 |
| Runnable cases | 104 |

## Domains

| Domain | Queries | Dataset status | Modalities | Expected files | Present dataset files |
|---|---:|---|---|---:|---:|
| agnews | 4 | materialized_complete | sqlite, bson | 1 | 2 |
| bookreview | 3 | materialized_complete | sqlite, sql | 2 | 2 |
| civic_unstructured | 10 | materialized_complete | sqlite, bson | 2 | 2 |
| crmarenapro | 13 | materialized_complete | sqlite, duckdb, sql | 6 | 6 |
| cve | 10 | materialized_complete | sqlite, duckdb, sql, files, bson | 2 | 5 |
| DEPS_DEV_V1 | 2 | materialized_complete | sqlite | 2 | 2 |
| GITHUB_REPOS | 4 | materialized_complete | sqlite | 2 | 2 |
| googlelocal | 4 | materialized_complete | sqlite, sql | 2 | 2 |
| imdb | 10 | materialized_complete | sqlite, sql | 2 | 2 |
| krama | 10 | materialized_complete | sqlite, bson | 3 | 3 |
| music_brainz_20k | 3 | materialized_complete | sqlite, duckdb | 1 | 2 |
| PANCANCER_ATLAS | 3 | materialized_complete | sqlite, sql | 2 | 2 |
| PATENTS | 3 | materialized_complete | sqlite, sql | 2 | 2 |
| stockindex | 3 | materialized_complete | sqlite | 2 | 2 |
| stockmarket | 5 | materialized_complete | sqlite | 2 | 2 |
| usaspending | 10 | materialized_complete | sqlite, duckdb, sql, files, bson | 2 | 5 |
| yelp | 7 | materialized_complete | sqlite, bson | 1 | 3 |

## Initial Splits

### train (62)

- `DEPS_DEV_V1/query1`
- `GITHUB_REPOS/query1`
- `PANCANCER_ATLAS/query1`
- `PATENTS/query1`
- `agnews/query1`
- `bookreview/query1`
- `civic_unstructured/query1`
- `crmarenapro/query1`
- `cve/query1`
- `googlelocal/query1`
- `imdb/query1`
- `krama/query1`
- `music_brainz_20k/query1`
- `stockindex/query1`
- `stockmarket/query1`
- `usaspending/query1`
- `yelp/query1`
- `DEPS_DEV_V1/query2`
- `GITHUB_REPOS/query2`
- `PANCANCER_ATLAS/query2`
- `PATENTS/query2`
- `agnews/query2`
- `bookreview/query2`
- `civic_unstructured/query2`
- `crmarenapro/query2`
- `cve/query2`
- `googlelocal/query2`
- `imdb/query2`
- `krama/query2`
- `music_brainz_20k/query2`
- `stockindex/query2`
- `stockmarket/query2`
- `usaspending/query2`
- `yelp/query2`
- `GITHUB_REPOS/query3`
- `PANCANCER_ATLAS/query3`
- `PATENTS/query3`
- `agnews/query3`
- `bookreview/query3`
- `civic_unstructured/query3`
- `crmarenapro/query3`
- `cve/query3`
- `googlelocal/query3`
- `imdb/query3`
- `krama/query3`
- `music_brainz_20k/query3`
- `stockindex/query3`
- `stockmarket/query3`
- `usaspending/query3`
- `yelp/query3`
- `GITHUB_REPOS/query4`
- `agnews/query4`
- `civic_unstructured/query4`
- `crmarenapro/query4`
- `cve/query4`
- `googlelocal/query4`
- `imdb/query4`
- `krama/query4`
- `stockmarket/query4`
- `usaspending/query4`
- `yelp/query4`
- `civic_unstructured/query5`

### dev (21)

- `crmarenapro/query5`
- `cve/query5`
- `imdb/query5`
- `krama/query5`
- `stockmarket/query5`
- `usaspending/query5`
- `yelp/query5`
- `civic_unstructured/query6`
- `crmarenapro/query6`
- `cve/query6`
- `imdb/query6`
- `krama/query6`
- `usaspending/query6`
- `yelp/query6`
- `civic_unstructured/query7`
- `crmarenapro/query7`
- `cve/query7`
- `imdb/query7`
- `krama/query7`
- `usaspending/query7`
- `yelp/query7`

### heldout (21)

- `civic_unstructured/query8`
- `crmarenapro/query8`
- `cve/query8`
- `imdb/query8`
- `krama/query8`
- `usaspending/query8`
- `civic_unstructured/query9`
- `crmarenapro/query9`
- `cve/query9`
- `imdb/query9`
- `krama/query9`
- `usaspending/query9`
- `civic_unstructured/query10`
- `crmarenapro/query10`
- `cve/query10`
- `imdb/query10`
- `krama/query10`
- `usaspending/query10`
- `crmarenapro/query11`
- `crmarenapro/query12`
- `crmarenapro/query13`

## Query Cases

| Query ID | Definition | Dataset | Runnable | Preview |
|---|---|---|---|---|
| `agnews/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the title of the sports article whose description has the greatest number of characters? |
| `agnews/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | What fraction of all articles authored by Amy Jones belong to the Science/Technology category? |
| `agnews/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the average number of business articles published per year in Europe from 2010 to 2020, inclusive? |
| `agnews/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | In 2015, which region published the largest number of articles in the World category? |
| `bookreview/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Which decade of publication (e.g., 1980s) has the highest average rating among decades with at least 10 distinct books that have been rated? Return the decade with the highest average rating. |
| `bookreview/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Which English-language books in the 'Literature & Fiction' category have a perfect average rating of 5.0? Return all matching books. |
| `bookreview/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | Which books categorized as 'Children's Books' have received an average rating of at least 4.5 based on reviews from 2020 onwards? |
| `civic_unstructured/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | As of 2023-01-01, list all projects whose most recent report (dated on or before 2023-01-01) records both a type of 'capital' and a status of 'design' and that have accumulated total funding of more than $500,000. Accumulated total funding  |
| `civic_unstructured/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | As of 2023-01-01, among all projects whose most recent report (dated on or before 2023-01-01) records a status of 'completed', which project has the highest accumulated total funding, and what is that funding amount in USD? Accumulated tota |
| `civic_unstructured/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | As of 2022-08-01, list all funding sources where at least 25% of the distinct projects they have funded on or before that date have a status of 'completed' in their most recent report dated on or before 2022-08-01. |
| `civic_unstructured/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the ratio of total funding amount granted to capital projects versus disaster projects between 2021-06-01 and 2022-06-01 (inclusive)? For each funding record, use the project's type (capital or disaster) as of the date that funding  |
| `civic_unstructured/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | Between 2021-06-01 and 2023-01-01, for all projects that underwent at least one status change (i.e., there exist at least two reports within this period that record different statuses for that project), what is the average total funding rec |
| `civic_unstructured/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | Across all years in the funding records, which year did capital projects receive the highest total funding amount? For each funding record, the project's type (capital or disaster) is determined by its most recent report dated on or before  |
| `civic_unstructured/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | As of 2022-11-01, list all projects whose most recent report (dated on or before 2022-11-01) records both a type of 'disaster' and a status of 'not started' and that have accumulated total funding of more than $1,000,000. Accumulated total  |
| `civic_unstructured/query8` | definition_ready | materialized_complete | runnable_if_dataset_available | As of 2022-06-01, among all projects whose most recent report (dated on or before 2022-06-01) records a type of 'capital' and a status of 'construction', which project has the lowest accumulated total funding, and what is that funding amoun |
| `civic_unstructured/query9` | definition_ready | materialized_complete | runnable_if_dataset_available | As of 2022-11-01, list all funding sources where more than 55% of the distinct projects they have funded on or before that date have a type of 'disaster' in their most recent report dated on or before 2022-11-01. |
| `civic_unstructured/query10` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the ratio of total funding granted to projects with a status of 'completed' versus projects with a status of 'not started' between 2021-09-01 and 2022-09-01 (inclusive)? For each funding record, the project's status is determined by |
| `crmarenapro/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Can this lead be qualified based on the latest discussions? If the answer is no, which factors—'Budget', 'Authority', 'Need', or 'Timeline'—are responsible? Return only one or several of the four BANT factors that the lead qualification fai |
| `crmarenapro/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Does the cost and setup of this quote comply with our company policy? If it doesn't, which knowledge article is it in conflict with? Return only the Id of the knowledge article that the quote violates. If no violation is found, return None. |
| `crmarenapro/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | Is the stage name accurately representing the tasks for this opportunity? If it is not, what should the appropriate stage name be? Return only the correct stage label among ('Qualification', 'Discovery', 'Quote', 'Negotiation', 'Closed'). - |
| `crmarenapro/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | Is there a particular month in the past 10 months where the number of SecureAnalytics Pro cases significantly exceeds those of other months? The associated product Id is 01tWt000006hVJdIAM. Return only the month name. - Today's date: 2021-0 |
| `crmarenapro/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | What has been the most frequent problem AI Cirku-Tech encountered over the past five months? The associated product Id is 01tWt000006hV8LIAU. Return only the issue Id of the most reported issue for this product. - Today's date: 2023-01-16 |
| `crmarenapro/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | Is the product setup in this quotation, including elements like quantity and price, against company regulations? Return only the Id of the knowledge article that the invalid config violates. ## Invalid config guide. Look for the relevant kn |
| `crmarenapro/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | Did the agent breach the policy, and if so, which knowledge article was breached? Return only the Id of the knowledge article or None if no violation is found. - Case Id to be considered is: 500Wt00000DDyznIAD |
| `crmarenapro/query8` | definition_ready | materialized_complete | runnable_if_dataset_available | Identify the agent with the fewest transfer counts in the last 4 quarters among those who handled more than 0 cases. Return only the Id of the agent. ## Transfer Count Policy - Definition: The number of instances a case was reassigned or tr |
| `crmarenapro/query9` | definition_ready | materialized_complete | runnable_if_dataset_available | Which states have the quickest case closure time in the past 6 quarters? Return only the two-letter abbreviation of the most matching state (eg. CA). - Today's date: 2022-10-26 |
| `crmarenapro/query10` | definition_ready | materialized_complete | runnable_if_dataset_available | In the past four months, which agent had the lowest average handle time for those processing more than one case? Return only the Id of the agent. ## Handle Time Policy - Definition: The duration taken to close a case. Specifically, it is th |
| `crmarenapro/query11` | definition_ready | materialized_complete | runnable_if_dataset_available | Can you show me the AI processing unit I purchased last month? Return only the Id of the product from the contact's relevant past transaction. - Contact Id interacting: 003Wt00000Jqy8SIAR - Today's date: 2021-07-15 |
| `crmarenapro/query12` | definition_ready | materialized_complete | runnable_if_dataset_available | Who had the quickest average turnaround from opening to closing opportunities among agents in April 2023? Return only the Id of the agent. ## Sales Cycle Policy - Definition: The sales cycle is measured as the number of days between an oppo |
| `crmarenapro/query13` | definition_ready | materialized_complete | runnable_if_dataset_available | Identify the agent who achieved the top sales figures for orders made in the past five months. Return only the Id of the agent. ## Sales Amount Policy - Definition: The sales amount for an order is calculated as the product of the quantity  |
| `cve/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct CVEs published in 2023 are listed in CISA's Known Exploited Vulnerabilities (KEV) catalog AND have at least one vulnerable Apache product configuration? |
| `cve/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Among CVEs in CISA's Known Exploited Vulnerabilities (KEV) catalog flagged as having known ransomware-campaign use, identify the canonical vendor (lowercase, using kev_vendor_aliases to resolve KEV vendor_project surface forms) whose CVEs i |
| `cve/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | How many entries in CISA's Known Exploited Vulnerabilities (KEV) catalog reference a CVE identifier for which there is NO matching record in the NVD vulnerability database (vulns_db)? |
| `cve/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | For each canonical vendor (using kev_vendor_aliases to resolve KEV vendor_project surface forms) that has at least 10 distinct CVEs which are BOTH listed in CISA's Known Exploited Vulnerabilities (KEV) catalog AND have at least one vulnerab |
| `cve/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | Among CVEs in CISA's Known Exploited Vulnerabilities (KEV) catalog that affect Apache Tomcat (canonical vendor 'apache', canonical product 'tomcat' per the CPE match list), how many distinct affected version strings are recorded, excluding  |
| `cve/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct CVEs have NO English-language description, DO have at least one non-English description, AND are listed in CISA's Known Exploited Vulnerabilities (KEV) catalog? |
| `cve/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | Among CPE match entries flagged as vulnerable AND whose CVE is listed in CISA's Known Exploited Vulnerabilities (KEV) catalog, which canonical (vendor, product) pair has the highest count of rows? Return as a single string in the form 'vend |
| `cve/query8` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct CVEs are listed in CISA's KEV catalog AND have at least one vulnerable Microsoft product configuration AND have a CVSS v3 base score of 7.0 or higher? Use the exact numeric score encoded as the first numeric token in vulns |
| `cve/query9` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct CVEs satisfy ALL of the following: they appear in MORE THAN ONE row of the cves table in vulns_db with conflicting cvss3_attack_vector values, AND they are listed in CISA's Known Exploited Vulnerabilities (KEV) catalog? |
| `cve/query10` | definition_ready | materialized_complete | runnable_if_dataset_available | Among the products listed in CISA's Known Exploited Vulnerabilities (KEV) catalog whose canonical vendor is Microsoft (using kev_vendor_aliases to resolve KEV vendor_project surface forms), how many distinct products have at least one assoc |
| `DEPS_DEV_V1/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Considering only the latest release versions for each distinct NPM package, which packages are the top 5 most popular based on the Github star number, as well as their versions? |
| `DEPS_DEV_V1/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Among all NPM packages with project license 'MIT' and marked as release, which 5 projects have the highest GitHub fork count? |
| `GITHUB_REPOS/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Among repositories that do not use Python, what proportion of their README.md files include copyright information? |
| `GITHUB_REPOS/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Identify the repository in Swift language that contains the most frequently copied non-binary Swift file in the dataset, ensuring that each file is uniquely determined by its ID. |
| `GITHUB_REPOS/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | How many commit messages are found in repositories that use the Shell programming language and are licensed under Apache-2.0, where each message exists, is shorter than 1,000 characters, and does not begin with 'merge', 'update', or 'test'? |
| `GITHUB_REPOS/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | List the repository names for the top five GitHub repositories whose main language is not Python, ordered by the highest number of commits. |
| `googlelocal/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | What are the top 5 businesses located in Los Angeles, California, ranked by highest average rating in descending order? |
| `googlelocal/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Which massage therapy businesses have an average rating of at least 4.0, and what are their respective average ratings? |
| `googlelocal/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | What are the top 5 businesses that remain open after 6:00 PM on at least one weekday, ranked by highest average rating? Include their names, operating hours, and average ratings. |
| `googlelocal/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | Which 3 businesses received the highest number of reviews with ratings of 4.5 or higher during 2019? Include their names and the count of high-rating reviews. |
| `imdb/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Among movies, TV movies, video movies, and video games produced after 1990 that are tagged with at least one keyword, are associated with a US company, have a US internet release date recorded in the 1990s or 2000s, and have a complete and  |
| `imdb/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Among writers who have a registered pseudonym and are credited on titles associated with a US company, what is the alphabetically first pseudonym and the alphabetically first title? |
| `imdb/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | Among female actresses credited with a voice role — including general voice, uncredited voice, Japanese dubbed version, or English dubbed version — in titles produced after 2000 that are associated with a US company and have a release date  |
| `imdb/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | Among cast and crew members whose name starts with 'Z' and who are credited in movies tagged with the keyword 'character-name-in-title' — indicating the movie's title contains a character's name — that are associated with at least one compa |
| `imdb/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | Among titles of kind 'movie' (excluding TV movies, video movies, and other title types) that have a release date and a rating on record and are associated with a US production company, what are the alphabetically first company name, the alp |
| `imdb/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | Among female actresses whose name contains 'An', who have a registered alternate name, played a named character, and have trivia on record, and who are credited with a voice role (general, uncredited, Japanese version, or English version) i |
| `imdb/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | Among cast and crew members who have a registered pseudonym and are credited in movies tagged with the keyword 'character-name-in-title' — indicating the movie's title contains a character's name — that are associated with a US company, wha |
| `imdb/query8` | definition_ready | materialized_complete | runnable_if_dataset_available | Among female actresses credited with a voice role — including general voice, uncredited voice, Japanese version, or English version — who have a registered alternate name (with the alternate name belonging to the same person holding the cre |
| `imdb/query9` | definition_ready | materialized_complete | runnable_if_dataset_available | Among male writers credited in a writing role — writer, head writer, written by, story, or story editor — on Horror or Thriller movies that are tagged with at least one of the keywords 'murder', 'violence', 'blood', 'gore', 'death', 'female |
| `imdb/query10` | definition_ready | materialized_complete | runnable_if_dataset_available | Among cast members who played a character whose name is not null and contains 'man' or 'Man', in titles of kind 'movie' produced after 2000, tagged with at least one of the keywords 'superhero', 'marvel-comics', 'based-on-comic', 'tv-specia |
| `krama/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | According to NIFC, among the regions that have a corresponding NIFC Geographic Area Coordination Center, which GACC accumulated the most human-caused wildfire acres from 2020 to 2023 (inclusive at both ends)? Use the latest report (by repor |
| `krama/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | According NIFC, from 2014 to 2024 (inclusive at both ends), which US state has the highest total number of lightning-caused wildfires across all NIFC Geographic Area Coordination Centers whose geographic boundaries intersect with that state |
| `krama/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the average number of reported identity thefts, as reported in 2024, across all US metropolitan statistical areas with a 2023 population exceeding one million? Estimate each MSA's 2023 population by linearly interpolating between it |
| `krama/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the absolute population change (in number of people) from 2020 to 2024 of the metropolitan statistical area with the highest reported identity theft rate per 100K population in the 2024 report? |
| `krama/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | From 2012 to 2018 (inclusive at both ends), what is the average water temperature (in °C) of the beach that had the most water samples that failed to meet bacterial water quality requirements? Consider only temperature readings collected wi |
| `krama/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | From 2008 to 2016 (inclusive at both ends), what is the bacterial exceedance rate (as a percentage, rounded to 2 decimal places) of the beach with the lowest average water temperature among all temperature readings collected in that period? |
| `krama/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | Among patients recorded in the UCEC_CPTAC3_meta_table_V2.1 sheet, what is the average age of patients whose hyperactivated protein is CDK12? Round to 2 decimal places. |
| `krama/query8` | definition_ready | materialized_complete | runnable_if_dataset_available | Among patients recorded in the UCEC_CPTAC3_meta_table_V2.1 sheet with Serous histologic type who were not excluded from the study, what is the hyperactivated protein of the oldest patient? |
| `krama/query9` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the mean Kp index, according to the 2024 OMNI2 low-resolution hourly data, for the calendar month in 2024 during which Swarm-B recorded its highest mean thermospheric density? Round to 4 decimal places. |
| `krama/query10` | definition_ready | materialized_complete | runnable_if_dataset_available | During the geomagnetic storm period captured in the space-track orbital observations for satellite NORAD 58214, what is the mean BSTAR drag coefficient of satellite NORAD 43180 as recorded in its TLE data? Round to 6 decimal places. |
| `music_brainz_20k/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | How much revenue in USD did Apple Music make from Beyoncé's song 'Get Me Bodied' in Canada? |
| `music_brainz_20k/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Which store earned the most revenue in USD from Brucqe Maginnis' song 'Street Hype' across all countries? |
| `music_brainz_20k/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | Which song generated the highest total revenue in USD across all stores and countries? |
| `PANCANCER_ATLAS/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | For LGG patients, compute the average log10-transformed expression of the IGF2 gene across different histology types. Only include patients with valid IGF2 expression values and histology annotations that are not enclosed in square brackets |
| `PANCANCER_ATLAS/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Among BRCA patients in the PanCancer Atlas who are alive, which top three histological types show the highest percentage of CDH1 gene mutations? |
| `PANCANCER_ATLAS/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | Calculate the chi-square statistic to assess the association between histological types and the presence of CDH1 gene mutations in female BRCA patients from the PanCancer Atlas, excluding categories with marginal totals less than or equal t |
| `PATENTS/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Identify the CPC technology areas with the highest exponential moving average of patent filings each year (smoothing factor 0.2), and return only the CPC group codes at level 5 whose best year is 2022. |
| `PATENTS/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Find the CPC technology areas in Germany with the highest exponential moving average of patent filings each year (smoothing factor 0.1) for patents granted in the second half of 2019. Include the full title, CPC group code, and the best yea |
| `PATENTS/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | Which assignees, excluding UNIV CALIFORNIA itself, have cited patents assigned to UNIV CALIFORNIA, and what are the titles of the primary CPC subclasses associated with these citations? Please provide the name of each citing assignee togeth |
| `stockindex/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | Which stock index in the Asia region has exhibited the highest average intraday volatility since 2020? |
| `stockindex/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Among North American stock indices, which indices had more up days than down days in 2018? |
| `stockindex/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | If an investor had made regular monthly investments in all indices since 2000, which 5 indices would have produced the highest overall returns, and what countries do they belong to? |
| `stockmarket/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | What was the maximum adjusted closing price in 2020 for The RealReal, Inc.? |
| `stockmarket/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | List all ETF securities listed on NYSE Arca that reached an adjusted closing price above $200 at any point during 2015, and also report the total number of such ETFs. |
| `stockmarket/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | List all company names on the NASDAQ-listed Market that were financially troubled (delinquent, deficient, or both) and have trading volume in 2008, for each, report its exisiting non-null average daily trading volume in 2008. |
| `stockmarket/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | What are the names (not symbol) of the top 5 non-ETF stocks listed on the New York Stock Exchange (NYSE) that had more up days than down days in 2017? (Up days: closing price > opening price; Down days: closing price < opening price) |
| `stockmarket/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | Which 5 companies listed on the NASDAQ Capital Market had the highest number of days in 2019 where the intraday price range exceeded 20% of the low price, list the company names please? |
| `usaspending/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct contract awards from the Department of Defense have an award amount greater than $1,000,000? |
| `usaspending/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | How many contract awards went to recipients located in California with an award amount greater than $1,000,000? |
| `usaspending/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct recipient UEIs are associated with contracts in NAICS sector 33? |
| `usaspending/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | Among awarding agencies that have issued at least 10 contracts, which agency has the highest proportion of contracts with an award amount greater than $1,000,000? Return the agency name, breaking ties alphabetically. |
| `usaspending/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct 2-digit NAICS sectors are represented among contracts with an award amount of at least $10,000,000? |
| `usaspending/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | How many distinct recipients in the recipients database are each associated with more than one UEI? |
| `usaspending/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | Among contracts with an award amount of at least $10,000,000, which 2-digit NAICS sector has the most contracts? Return the 2-digit sector code, breaking ties by the smaller code. |
| `usaspending/query8` | definition_ready | materialized_complete | runnable_if_dataset_available | How many contract awards were made to Lockheed Martin by the Department of Defense with an award amount greater than $1,000,000? |
| `usaspending/query9` | definition_ready | materialized_complete | runnable_if_dataset_available | How many contracts have no English-language description and an award amount greater than $1,000,000? |
| `usaspending/query10` | definition_ready | materialized_complete | runnable_if_dataset_available | Among the top 10 most active contract recipients by total number of contracts, how many of their contracts have a superseded amount entry on record? |
| `yelp/query1` | definition_ready | materialized_complete | runnable_if_dataset_available | What is the average rating of all businesses located in Indianapolis, Indiana? |
| `yelp/query2` | definition_ready | materialized_complete | runnable_if_dataset_available | Which U.S. state has the highest number of reviews, and what is the average rating of businesses in that state? |
| `yelp/query3` | definition_ready | materialized_complete | runnable_if_dataset_available | During 2018, how many businesses that received reviews offered either business parking or bike parking? |
| `yelp/query4` | definition_ready | materialized_complete | runnable_if_dataset_available | Which business category has the largest number of businesses that accept credit card payments, and what is its average rating? |
| `yelp/query5` | definition_ready | materialized_complete | runnable_if_dataset_available | Which U.S. state has the highest number of businesses that offer WiFi, and what is the average rating for those businesses? |
| `yelp/query6` | definition_ready | materialized_complete | runnable_if_dataset_available | Which business received the highest average rating between January 1, 2016 and June 30, 2016, and what category does it belong to? Consider only businesses with at least 5 reviews. |
| `yelp/query7` | definition_ready | materialized_complete | runnable_if_dataset_available | Among users who registered on Yelp in 2016, which 5 business categories have received the most total reviews from those users since 2016? |
