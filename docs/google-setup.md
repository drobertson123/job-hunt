# Google Cloud Setup for Gmail Connector

This guide walks through connecting Opportunity Hunter to your Gmail account so
it can ingest messages as Communications.

## 1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Click the project selector at the top → **New Project**.
3. Name it (e.g. `opportunity-hunter`) and click **Create**.

## 2. Enable the Gmail API

1. In the new project, go to **APIs & Services → Library**.
2. Search for **Gmail API** and click **Enable**.

## 3. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**.
2. Choose **External** and click **Create**.
3. Fill in the required fields (App name, user support email, developer email).
4. On the **Test users** page, add your Gmail address as a test user.
5. Save and continue through all screens.

## 4. Create an OAuth client ID

1. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Choose **Desktop app** as the application type.
3. Give it a name (e.g. `Opportunity Hunter local`) and click **Create**.
4. Copy the **Client ID** and **Client secret** shown in the dialog.

> **Loopback note:** Desktop app clients allow loopback (`127.0.0.1`) redirects
> automatically — no need to add `http://127.0.0.1:8000/api/google/oauth/callback`
> to an allowlist in the Google Cloud console.

## 5. Enter credentials in Opportunity Hunter

1. Open the Opportunity Hunter UI and click the badge in the top-right corner.
2. Paste the **Google client ID** and **Google client secret** into the
   respective fields and click **Save**.

## 6. Connect your Google account

> **Important:** You must click **Connect Google** from the *same machine running
> the Opportunity Hunter server*, because the OAuth redirect goes to
> `http://127.0.0.1:8000` (loopback).

1. After saving credentials, a **Connect Google** link appears in the Settings
   panel.
2. Click it — a new tab opens and redirects to Google's consent screen.
3. Sign in and grant access.
4. You will see "Google connected ✓" — close the tab.

## 7. Sync Gmail

1. Back in the Settings panel, click **Sync Gmail**.
2. The connector fetches up to 50 messages from the last 30 days and creates
   Communication rows for each.
3. Ingested mail appears under **Attention → Untriaged messages** and can be
   triaged with the `email-analyser` capability.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Set Google client id/secret in Settings first" (400) | Credentials not saved yet — do Step 5. |
| "invalid oauth state" (400) | State mismatch; retry the Connect flow. |
| "Google account not connected" (500 during sync) | Complete the OAuth flow (Step 6) first. |
| Consent screen shows "App not verified" warning | Expected for External apps in test mode; click **Continue**. |
