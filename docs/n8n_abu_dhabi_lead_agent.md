# Abu Dhabi Daily Lead Outreach Automation

This guide explains how to deploy the included n8n workflow and Python helper
script so that Bluechip Gulf IT Services can automatically collect 49 new Abu
Dhabi business email leads every morning at 9:00 AM Gulf Standard Time (GST) and
send each contact the company profile.

The workflow focuses on non-IT establishments (offices, factories, warehouses,
public sector organisations, healthcare, education, hospitality, oil & gas,
marine, retail, etc.) and guarantees that no email address is reused on later
runs.

## Repository contents

| File | Purpose |
| ---- | ------- |
| `automation/lead_selector.py` | Fetches 2GIS Abu Dhabi listings, filters out IT systems integrators, enforces the 49 email daily target, and updates the lead history file so contacts are never repeated. |
| `data/contact_history.json` | Created automatically on first run to persist already-contacted emails. |
| `output/daily_leads.json` & `output/daily_leads.csv` | Generated on each run; contain the 49 fresh leads in JSON/CSV format for audit or CRM upload. |
| `n8n/workflows/abu_dhabi_lead_generation.json` | Importable n8n workflow that orchestrates the cron trigger, Python script, email preparation, and daily outreach. |
| `assets/company_profile.pdf` | Place your Bluechip Gulf IT Services profile here so the workflow can attach it to every email. |

## Prerequisites

1. **2GIS API key** – request an API key from 2GIS. Store it in the n8n host
   environment as `DGIS_API_KEY`.
2. **Python 3.9+ with requests** – install dependencies inside the same
   environment that runs n8n: `pip install -r requirements.txt`.
3. **Company profile PDF** – save your latest profile as
   `assets/company_profile.pdf` (same directory as this repository).
4. **SMTP credentials** – configure an n8n SMTP credential for the sender
   account (e.g., `sales@bluechipgulf.ae`).

## Configuring the Python lead collector

The collector uses the 2GIS Catalog API to query Abu Dhabi (`region_id` defaults
to `70000001017325107`), filters out obvious IT system integrators, and writes
unique leads. You can tweak its behaviour via CLI flags:

```bash
python3 automation/lead_selector.py \
  --limit 49 \
  --region-id 70000001017325107 \
  --history data/contact_history.json \
  --categories "List of Words.txt" \
  --json-output output/daily_leads.json \
  --csv-output output/daily_leads.csv
```

Environment variables:

- `DGIS_API_KEY` – required; 2GIS access token.
- `SENDER_NAME`, `SENDER_EMAIL`, `SENDER_PHONE` – optional; override email
  signature defaults inside the workflow.

The script prints a JSON summary to STDOUT so n8n can respond to failures and
stores every emailed address in `data/contact_history.json`. The history file
caps at 10,000 emails and guarantees each day’s 49 addresses have never been
suggested before.

## Importing the n8n workflow

1. Open n8n → **Import from File** → select
   `n8n/workflows/abu_dhabi_lead_generation.json`.
2. Edit the **Execute Command** node if the repository path is different in your
   deployment.
3. Set the SMTP credential on the **Send Company Profile** node.
4. Activate the workflow after a dry run.

Workflow outline:

1. **Daily 9AM Trigger** – runs at 09:00 GST (cron: `0 9 * * *`).
2. **Collect Fresh Leads** – runs the Python script to fetch 49 new Abu Dhabi
   contacts; updates the history file.
3. **Load Lead List** – converts the JSON output into n8n items.
4. **Load Company Profile** – reads the PDF attachment once per run.
5. **Attach Profile** – merges lead data with the binary attachment.
6. **Send One-by-One** – iterates through the 49 leads.
7. **Prepare Email Payload** – personalises the body and subject while keeping
   the profile attachment.
8. **Send Company Profile** – sends the email via SMTP, one contact at a time.
9. **Summarise Run** – re-reads `output/daily_leads.json` to produce a digest
   (can be extended to push into Slack/CRM or an audit email).

## Daily operations & monitoring

- Review `output/daily_leads.csv` if you need to import the leads into a CRM.
- The cron schedule runs automatically; use n8n’s execution log to confirm each
  day’s outreach and catch any API/email failures.
- If you ever want to “forget” a contact (e.g., opt-outs), remove their email
  from `data/contact_history.json` manually.

## Suggested enhancements

1. **Email validation & bounce protection** – add a ZeroBounce/Kickbox node to
   validate each address before sending, reducing bounce rate and protecting the
   sender reputation.
2. **Intent scoring** – enrich leads with external data (e.g., Clearbit, Apollo)
   and prioritise those expanding headcount or infrastructure to focus on
   higher-probability prospects.
3. **CRM sync** – push the daily CSV into HubSpot, Zoho, or Dynamics via n8n so
   the sales team has instant visibility, reminders, and follow-up sequences.
4. **Follow-up cadences** – create a secondary workflow that triggers two and
   seven days later for follow-up emails on opens or clicks, ensuring consistent
   nurturing.
5. **Performance analytics** – log send/open/click metrics into a BI store
   (BigQuery, Superset) so you can track conversion performance by industry and
   adjust targeting.
6. **Opt-out handling** – add a webhook and database table to honour unsubscribe
   requests automatically and keep the history file in sync.

By combining the Python collector with the n8n workflow you can reliably reach
49 fresh Abu Dhabi organisations every morning without repeating contacts or
mailing IT system integrators.
