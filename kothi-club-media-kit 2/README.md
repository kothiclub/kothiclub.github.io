# Kothi Club media kit

A one-page media kit that refreshes itself from Instagram every morning: followers across
platforms, 30-day reach, average reel views/reach/shares, engagement rate, top reels and posts,
follower demographics and your rate card.

No terminal needed. Everything is done in the browser.

```
index.html                     the page (design)
data/site.json                 YOU edit this: tagline, rates, packages, terms, contact
data/live.json                 written automatically, don't edit
media/                         thumbnails of top reels/posts, saved automatically
scripts/update.py              fetches the numbers from Instagram
.github/workflows/refresh.yml  runs the script daily at 6:00 AM IST
```

## Setup

### A. Put the site online (GitHub Pages)
1. github.com → Sign up (free).
2. "+" → New repository → name `kothiclub` → Public → Create.
3. "uploading an existing file" → drag in everything from this folder (unzip first) → Commit.
   If the `.github` folder doesn't upload (hidden folder), create it by hand:
   Add file → Create new file → name `.github/workflows/refresh.yml` → paste its contents → Commit.
4. Settings → Pages → Source: Deploy from a branch → `main` / `(root)` → Save.
5. After 1–2 minutes the site is at `https://YOUR-USERNAME.github.io/kothiclub/`
   (with sample numbers and a black banner).

### B. Make a Meta app
1. developers.facebook.com → log in with the Facebook account that is admin of the Kothi Club Page.
2. My Apps → Create app → use case "Other" / type "Business" → name "Kothi Club Media Kit".
3. Add product → Instagram → "API setup with Facebook login".
   Leave the app in Development mode. It only reads your own account; no App Review needed.

### C. Get a token that never expires
1. developers.facebook.com/tools/explorer
2. Meta App: Kothi Club Media Kit. User or Page: Get User Access Token.
3. Tick: instagram_basic, instagram_manage_insights, pages_show_list,
   pages_read_engagement, business_management → Generate → allow everything, select the Kothi Club Page + Instagram.
4. Click the blue "i" next to the token → Open in Access Token Tool → "Extend Access Token" → copy the new token.
5. Back in the Explorer, paste that long token, then run:
   `me/accounts?fields=name,access_token,instagram_business_account`
6. From the result, copy the Kothi Club Page's `access_token` (never expires)
   and `instagram_business_account.id` (starts with 1784).

### D. Connect it to GitHub
1. Repo → Settings → Secrets and variables → Actions → New repository secret:
   - `IG_ACCESS_TOKEN` = the Page access_token
   - `IG_USER_ID` = the 1784… id
2. Actions tab → enable workflows if asked → "Refresh Instagram stats" → Run workflow.
3. Green tick after 1–3 minutes → refresh your site: banner gone, real numbers in.

Facebook follower count comes in automatically with the Page token.
YouTube (optional): Google Cloud Console → enable YouTube Data API v3 → API key →
add secrets `YT_API_KEY` and `YT_CHANNEL_ID` (UC…). Otherwise the number in site.json is shown.

## Editing
- Rates, packages, text, contact: open `data/site.json` on GitHub → pencil icon → edit → Commit.
  Live in about a minute.
- `"show_prices": false` hides every price and shows "On request".
- `whatsapp`: digits with country code, e.g. `"919876543210"`.
- Design changes: edit `index.html` the same way, or ask Claude and paste the new file in.

## Good to know
- Read-only: the app cannot post, delete or change anything on Instagram and does not affect reach.
- Never put the token in a file or a chat. It belongs only in GitHub Secrets.
- The page has `noindex`, so Google won't list it; only people with the link find it.
  Remove that line in index.html if you want it searchable.
- Reels younger than 3 days are left out of averages.
- Instagram data can lag up to 48 hours. Demographics need 100+ followers.
- If the run turns red, open it in the Actions tab; the error says why
  (usually the token was regenerated or a permission is missing → redo step C).
- If you change your Facebook password or remove the app, the token stops working → redo step C.
