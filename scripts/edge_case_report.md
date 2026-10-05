# Edge-case report

API http://localhost:8000 · credits used 0 of cap 60 · PASS 148 · UNVERIFIABLE 7

| Section | Check | Result | Detail |
|---|---|---|---|
| A | query empty → 422 | PASS |  |
| A | query one character → 422 | PASS |  |
| A | query 121 characters → 422 | PASS |  |
| A | query emoji only → 422 | PASS |  |
| A | query only spaces → 422 | PASS |  |
| A | query digits only → 422 | PASS |  |
| A | query Hindi script → 422 | PASS |  |
| A | PIN letters → 422 | PASS |  |
| A | PIN starts with 0 → 422 | PASS |  |
| A | PIN 5 digits → 422 | PASS |  |
| A | PIN 7 digits → 422 | PASS |  |
| A | PIN empty → 422 | PASS |  |
| A | prescription 0 lines → 4xx | PASS |  |
| A | prescription 9 lines → 4xx | PASS |  |
| A | prescription tablets 0 → 4xx | PASS |  |
| A | prescription tablets 501 → 4xx | PASS |  |
| A | prescription tablets true → 4xx | PASS |  |
| A | prescription tablets "10" → 4xx | PASS |  |
| A | prescription tablets 2.5 → 4xx | PASS |  |
| A | prescription missing q → 4xx | PASS |  |
| A | prescription malformed JSON → 4xx | PASS |  |
| A | prescription not a list → 4xx | PASS |  |
| A | search with hostile text '<script>alert(1)</script>' → JSON, no 5xx | PASS |  |
| A | search with hostile text "' OR 1=1 --" → JSON, no 5xx | PASS |  |
| A | search with hostile text '../../etc/passwd' → JSON, no 5xx | PASS |  |
| A | prescription with hostile text '[{"q":"<script>alert(1)</scrip' → JSON, no 5xx | PASS |  |
| A | unknown link id → 404 | PASS |  |
| B | typo 'dollo 650' → Dolo listings | PASS |  |
| C | typo 'dollo 650' → Dolo listings: 20 shown prices = delivery rules | PASS |  |
| C | typo 'dollo 650' → Dolo listings: delivered rows ranked by landed cost, before the rest | PASS |  |
| C | typo 'dollo 650' → Dolo listings: cheapest flag on the lowest landed cost | PASS |  |
| D | typo 'dollo 650' → Dolo listings: SastaSundar · Dolo 650 mg → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings: SastaSundar · Dolo 650 mg → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings: Kogland Commerce · Dolo 650 Tablet - Strip of 15 → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings: Kogland Commerce · Dolo 650 Tablet - Strip of 15 → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings: 1mg · Dolo 650 Tablet → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings: 1mg · Dolo 650 Tablet → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings: Dawaa Dost · Micro Labs Dolo 650mg Tablets 15s → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings: Dawaa Dost · Micro Labs Dolo 650mg Tablets 15s → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings: Medizinhub · Dolo 650 Mg Tablet → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings: Medizinhub · Dolo 650 Mg Tablet → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Netmeds · Dolo 650 Tablet 15's → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Netmeds · Dolo 650 Tablet 15's → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Truemeds · Dolo 650 Tablet 15 → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Truemeds · Dolo 650 Tablet 15 → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Apollo Pharmacy · Dolo-650 Tablet 15's → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Apollo Pharmacy · Dolo-650 Tablet 15's → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Chemist180 · Dolo 650MG Tablet → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Chemist180 · Dolo 650MG Tablet → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): PharmEasy · Dolo 650mg Strip Of 15 Tablets → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): PharmEasy · Dolo 650mg Strip Of 15 Tablets → page loads and names the brand | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Medplus · Dolo 650MG Tab → URL names brand + strength | PASS |  |
| D | typo 'dollo 650' → Dolo listings (on click): Medplus · Dolo 650MG Tab → page loads | UNVERIFIABLE | HTTP 403: the pharmacy blocks scripted visits |
| B | typo 'stamloo 5' → Stamlo listings | PASS |  |
| C | typo 'stamloo 5' → Stamlo listings: 18 shown prices = delivery rules | PASS |  |
| C | typo 'stamloo 5' → Stamlo listings: delivered rows ranked by landed cost, before the rest | PASS |  |
| C | typo 'stamloo 5' → Stamlo listings: cheapest flag on the lowest landed cost | PASS |  |
| D | typo 'stamloo 5' → Stamlo listings (on click): SastaSundar · Stamlo 5 mg Tablet (30 Tab) → URL names brand + strength | PASS |  |
| D | typo 'stamloo 5' → Stamlo listings (on click): SastaSundar · Stamlo 5 mg Tablet (30 Tab) → page loads and names the brand | PASS |  |
| D | typo 'stamloo 5' → Stamlo listings (on click): Medivik · Stamlo 5mg Tablet → URL names brand + strength | PASS |  |
| D | typo 'stamloo 5' → Stamlo listings (on click): Medivik · Stamlo 5mg Tablet → page loads and names the brand | PASS |  |
| D | typo 'stamloo 5' → Stamlo listings · cheaper brand (on click): SastaSundar · Amodep 5 mg Tablet (15 Tab) → URL names brand + strength | PASS |  |
| D | typo 'stamloo 5' → Stamlo listings · cheaper brand (on click): SastaSundar · Amodep 5 mg Tablet (15 Tab) → page loads and names the brand | PASS |  |
| B | salt without strength → choose, 0 credits | PASS |  |
| B | brand without strength → choose | PASS |  |
| B | combination 'Pan-D' | PASS |  |
| C | combination 'Pan-D': 14 shown prices = delivery rules | PASS |  |
| C | combination 'Pan-D': delivered rows ranked by landed cost, before the rest | PASS |  |
| C | combination 'Pan-D': cheapest flag on the lowest landed cost | PASS |  |
| D | combination 'Pan-D' (on click): SastaSundar · Pan D Capsule (15 Cap) → URL names brand + strength | PASS |  |
| D | combination 'Pan-D' (on click): SastaSundar · Pan D Capsule (15 Cap) → page loads and names the brand | PASS |  |
| D | combination 'Pan-D' (on click): Medivik · Pan-d Capsule → URL names brand + strength | PASS |  |
| D | combination 'Pan-D' (on click): Medivik · Pan-d Capsule → page loads and names the brand | PASS |  |
| D | combination 'Pan-D' · cheaper brand (on click): Truemeds · Pantosec D Sr Capsule 15 → URL names brand + strength | PASS |  |
| D | combination 'Pan-D' · cheaper brand (on click): Truemeds · Pantosec D Sr Capsule 15 → page loads and names the brand | PASS |  |
| D | combination 'Pan-D' · cheaper brand (on click): 1mg · Pantodac-DSR 15 Capsules by wellness for | UNVERIFIABLE | product page not found or not this product; store search shown instead |
| B | syrup 'Benadryl cough syrup' | PASS |  |
| C | syrup 'Benadryl cough syrup': 10 shown prices = delivery rules | PASS |  |
| C | syrup 'Benadryl cough syrup': delivered rows ranked by landed cost, before the rest | PASS |  |
| C | syrup 'Benadryl cough syrup': cheapest flag on the lowest landed cost | PASS |  |
| D | syrup 'Benadryl cough syrup' (on click): Medivik · Benadryl Cough Syrup → URL names brand + strength | PASS |  |
| D | syrup 'Benadryl cough syrup' (on click): Medivik · Benadryl Cough Syrup → page loads | UNVERIFIABLE | SSLError |
| D | syrup 'Benadryl cough syrup' (on click): Dawaa Dost · Johnson & Johnson Benadryl Cough Syrup 5 | UNVERIFIABLE | no product page on Google for this listing; store search shown instead |
| B | non-medicine 'iphone 15' → no substitutes | PASS |  |
| B | gibberish 'xqzv 999' | PASS |  |
| B | shouting + padding '  DOLO   650  ' | PASS |  |
| C | shouting + padding '  DOLO   650  ': 20 shown prices = delivery rules | PASS |  |
| C | shouting + padding '  DOLO   650  ': delivered rows ranked by landed cost, before the rest | PASS |  |
| C | shouting + padding '  DOLO   650  ': cheapest flag on the lowest landed cost | PASS |  |
| D | shouting + padding '  DOLO   650  ' (on click): SastaSundar · Dolo 650 mg → URL names brand + strength | PASS |  |
| D | shouting + padding '  DOLO   650  ' (on click): SastaSundar · Dolo 650 mg → page loads and names the brand | PASS |  |
| D | shouting + padding '  DOLO   650  ' (on click): Kogland Commerce · Dolo 650 Tablet - Strip of 15 → URL names brand + strength | PASS |  |
| D | shouting + padding '  DOLO   650  ' (on click): Kogland Commerce · Dolo 650 Tablet - Strip of 15 → page loads and names the brand | PASS |  |
| B | unserviceable PIN 744101 → nothing delivered | PASS |  |
| C | unserviceable PIN 744101 → nothing delivered: 8 shown prices = delivery rules | PASS |  |
| C | unserviceable PIN 744101 → nothing delivered: delivered rows ranked by landed cost, before the rest | PASS |  |
| D | unserviceable PIN 744101 → nothing delivered (on click): Apollo Pharmacy · Stamlo-5 Tablet 15's → URL names brand + strength | PASS |  |
| D | unserviceable PIN 744101 → nothing delivered (on click): Apollo Pharmacy · Stamlo-5 Tablet 15's → page loads and names the brand | PASS |  |
| D | unserviceable PIN 744101 → nothing delivered (on click): PharmEasy · Stamlo 5Mg Strip Of 30 Tablets → URL names brand + strength | PASS |  |
| D | unserviceable PIN 744101 → nothing delivered (on click): PharmEasy · Stamlo 5Mg Strip Of 30 Tablets → page loads and names the brand | PASS |  |
| B | remote PIN 781001 Guwahati | PASS |  |
| C | remote PIN 781001 Guwahati: 20 shown prices = delivery rules | PASS |  |
| C | remote PIN 781001 Guwahati: delivered rows ranked by landed cost, before the rest | PASS |  |
| C | remote PIN 781001 Guwahati: cheapest flag on the lowest landed cost | PASS |  |
| D | remote PIN 781001 Guwahati (on click): SastaSundar · Dolo 650 mg → URL names brand + strength | PASS |  |
| D | remote PIN 781001 Guwahati (on click): SastaSundar · Dolo 650 mg → page loads and names the brand | PASS |  |
| D | remote PIN 781001 Guwahati (on click): 1mg · Dolo 650 Tablet → URL names brand + strength | PASS |  |
| D | remote PIN 781001 Guwahati (on click): 1mg · Dolo 650 Tablet → page loads and names the brand | PASS |  |
| B | remote PIN 190001 Srinagar | PASS |  |
| C | remote PIN 190001 Srinagar: 18 shown prices = delivery rules | PASS |  |
| C | remote PIN 190001 Srinagar: delivered rows ranked by landed cost, before the rest | PASS |  |
| C | remote PIN 190001 Srinagar: cheapest flag on the lowest landed cost | PASS |  |
| D | remote PIN 190001 Srinagar (on click): SastaSundar · Stamlo 5 mg Tablet (30 Tab) → URL names brand + strength | PASS |  |
| D | remote PIN 190001 Srinagar (on click): SastaSundar · Stamlo 5 mg Tablet (30 Tab) → page loads and names the brand | PASS |  |
| D | remote PIN 190001 Srinagar (on click): 1mg · Stamlo 5 Tablet → URL names brand + strength | PASS |  |
| D | remote PIN 190001 Srinagar (on click): 1mg · Stamlo 5 Tablet → page loads and names the brand | PASS |  |
| D | remote PIN 190001 Srinagar · cheaper brand (on click): SastaSundar · Amodep 5 mg Tablet (15 Tab) → URL names brand + strength | PASS |  |
| D | remote PIN 190001 Srinagar · cheaper brand (on click): SastaSundar · Amodep 5 mg Tablet (15 Tab) → page loads and names the brand | PASS |  |
| B | Meerut 250002 with links | PASS |  |
| C | Meerut 250002 with links: 18 shown prices = delivery rules | PASS |  |
| C | Meerut 250002 with links: delivered rows ranked by landed cost, before the rest | PASS |  |
| C | Meerut 250002 with links: cheapest flag on the lowest landed cost | PASS |  |
| D | Meerut 250002 with links: SastaSundar · Stamlo 5 mg Tablet (30 Tab) → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links: SastaSundar · Stamlo 5 mg Tablet (30 Tab) → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links: Medivik · Stamlo 5mg Tablet → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links: Medivik · Stamlo 5mg Tablet → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links: 1mg · Stamlo 5 Tablet → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links: 1mg · Stamlo 5 Tablet → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links: Apollo Pharmacy · Stamlo-5 Tablet 15's → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links: Apollo Pharmacy · Stamlo-5 Tablet 15's → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links: Chemist180 · Stamlo 5MG Tablet → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links: Chemist180 · Stamlo 5MG Tablet → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links (on click): Apollo Pharmacy · Stamlo-5 Tablet 30's → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links (on click): Apollo Pharmacy · Stamlo-5 Tablet 30's → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links (on click): PharmEasy · Stamlo 5Mg Strip Of 30 Tablets → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links (on click): PharmEasy · Stamlo 5Mg Strip Of 30 Tablets → page loads and names the brand | PASS |  |
| D | Meerut 250002 with links (on click): Medplus · Stamlo 5MG Tab → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links (on click): Medplus · Stamlo 5MG Tab → page loads | UNVERIFIABLE | HTTP 403: the pharmacy blocks scripted visits |
| D | Meerut 250002 with links · cheaper brand: SastaSundar · Amodep 5 mg Tablet (15 Tab) → URL names brand + strength | PASS |  |
| D | Meerut 250002 with links · cheaper brand: SastaSundar · Amodep 5 mg Tablet (15 Tab) → page loads and names the brand | PASS |  |
| E | 3 medicines + a strength-less line: HTTP 200 | PASS |  |
| E | 3 medicines + a strength-less line · cheapest: totals = items + rules' fees | PASS |  |
| E | 3 medicines + a strength-less line · one pharmacy: totals = items + rules' fees | PASS |  |
| E | 3 medicines + a strength-less line · as prescribed: totals = items + rules' fees | PASS |  |
| E | 3 medicines + a strength-less line: strength-less / unsold lines reported | PASS |  |
| E | 3 medicines + a strength-less line: every order line has a product link | PASS |  |
| D | 3 medicines + a strength-less line basket: SastaSundar · Amodep 5 mg Tablet (15 Tab) | UNVERIFIABLE | no product page on Google for this listing; store search shown instead |
| D | 3 medicines + a strength-less line basket: SastaSundar · Dolo 650 mg | UNVERIFIABLE | no product page on Google for this listing; store search shown instead |
| E | duplicate line + gibberish line: HTTP 200 | PASS |  |
| E | duplicate line + gibberish line · cheapest: totals = items + rules' fees | PASS |  |
| E | duplicate line + gibberish line · one pharmacy: totals = items + rules' fees | PASS |  |
| E | duplicate line + gibberish line · as prescribed: totals = items + rules' fees | PASS |  |
| E | duplicate line + gibberish line: strength-less / unsold lines reported | PASS |  |
| F | 8 concurrent searches: only 200 or 429 | PASS |  |
| F | every search slot released | PASS |  |
