# PharmaWatch

## Slide 1: Why PharmaWatch?

- Medicine prices vary across Indian online pharmacies.
- Patients often compare multiple platforms manually.
- Chronic-care patients repeatedly purchase the same medicines.
- Urgent searches require fast, reliable results.

**Target users:**

- Patients and caregivers
- Chronic disease patients
- Pharmacists
- Price-sensitive households

---

## Slide 2: SerpApi as the Search Layer

- `google_shopping`: medicine price discovery
- `composition database`: a generic medicine name (along with dosage) is attached with the medicine name being searched
- `google_scholar`: generic-equivalence verification
- Future OCR layer: prescription-to-medicine extraction

**Flow:**

```text
Medicine name
      ↓
SerpApi search
      ↓
Indian pharmacy listings
      ↓
Filtered and ranked results
```

---

## Slide 3: What the User Gets

- Medicine name and dosage
- Prices across pharmacy platforms
- Delivery fee and estimated delivery time
- Cheapest delivered option
- Availability and product link
- Verified generic alternative when evidence exists
- Cache status: `HIT` or `MISS`

> The lowest realistic delivered price, not just the lowest listed price.

---

## Slide 4: The Problem with Repeated Search

### Without caching

- Repeated searches call SerpApi again.
- API credits are consumed repeatedly.
- Users wait for the same information.

### With caching

- Previous results are reused.
- Similar queries can produce cache hits.
- Results return significantly faster.

```text
First request:
Medicine query → SerpApi → Redis cache

Repeat request:
Medicine query → Semantic cache → Instant result
```

---

## Slide 5: Semantic Cache

Different wording can represent the same intent:

```text
“Metformin 500mg price India”
“Metformin 500 mg cost India”
```

The cache:

1. Converts the query into a 384-dimensional embedding.
2. Compares it with cached query embeddings.
3. Calculates cosine similarity.
4. Returns a cached result above the similarity threshold.

**Similarity threshold:** `0.80`    [to be tested then reported]

**Dosage protection:**

```text
Metformin 20mg ≠ Metformin 200mg
```
[is accounted for]

---

## Slide 6: Performance and Reliability

- **7.08 seconds:** live SerpApi request
- **0.0099 seconds:** cache hit
- **710x faster:** measured speedup

**Reliability features:**

- Redis persistence
- TTL-based expiry
- Dosage-aware matching
- Passthrough mode if Redis is unavailable
- Offline verification tests

---

## Slide 7: Filtering and Distillation

Raw search results are converted into clean medicine listings.

**Retained fields:**
[have to be checked]

- Medicine name
- Platform
- Price in INR
- Availability
- Product link
- Delivery information

**Removed noise:**

- Advertisements
- Irrelevant products
- International sellers
- Duplicate listings
- Untrusted domains

**Supported platforms include:**

- Tata 1mg
- PharmEasy
- Netmeds
- Apollo Pharmacy
- MedPlus
- TrueMeds
- DawaaDost
- Magicine Pharma
- chemist180
- medivik (and more)          [should this be added or names]

---

## Slide 8: Cheapest Delivered Option

The cheapest listing is not always the cheapest order.

The system considers:

- PIN-code zone
- Platform delivery fee
- Free-delivery threshold
- Estimated delivery time
- Serviceability
- Platform fee

```text
Medicine price
+ Delivery fee
+ Platform fee
= Estimated landed cost
```

**Location categories:**

- Metro
- Tier 2
- Tier 3
- Remote
- Unserviceable

---

## Slide 9: Safer Generic Alternatives

```text
Composition database
          ↓
Generic candidate
          ↓
Google Scholar verification
          ↓
Confidence threshold
          ↓
Verified alternative
```

- Use curated medicine compositions as the primary source.
- Cross-check equivalence evidence through Google Scholar.
- Clearly label AI estimates.
- Show alternatives only when evidence meets the threshold.
- Otherwise display: **No verified alternative found**

---

## Slide 10: End-to-End Architecture

```text
User input
(text / future prescription OCR / voice)
             ↓
PharmaWatch agent
             ↓
Semantic cache
             ↓
SerpApi search
             ↓
Distiller and filters
             ↓
Price comparator
             ↓
Delivery estimator
             ↓
Generic verification
             ↓
Actionable result
```

**Technology stack:**

- Python
- SerpApi
- Sentence Transformers
- Redis
- Docker
- Planned Streamlit interface

---

## Slide 11: Impact and Roadmap

### Current foundation

- Semantic SerpApi cache
- Redis persistence
- Dosage guard
- TTL support
- Verification scripts
- Medicine composition database

### Next milestones

- Complete result distillation
- Add price ranking and change detection
- Implement delivery-cost calculations
- Complete generic verification
- Build the Streamlit dashboard
- Add robust prescription OCR
- Demonstrate cache savings in the live workflow

> PharmaWatch turns medicine search into a faster, cheaper, evidence-aware buying decision.