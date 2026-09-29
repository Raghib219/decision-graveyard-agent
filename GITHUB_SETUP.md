# GitHub Setup Instructions

## Step 1: Create GitHub Repository

1. Go to: **https://github.com/new**
2. Repository name: `decision-graveyard-agent`
3. Description: `AI agent that prevents companies from repeating failed decisions. Uses Hindsight Cloud + Groq LLM for semantic memory and real-time reasoning.`
4. **Make it PUBLIC** (for hackathon visibility)
5. **DO NOT** initialize with README, .gitignore, or license (we already have them)
6. Click **"Create repository"**

---

## Step 2: Push Your Code

After creating the repo, GitHub will show you commands. Run these in your terminal:

```powershell
cd "c:\Users\raghi\OneDrive\Desktop\Decision_Graveyard_agent"

# Add GitHub as remote (replace YOUR-USERNAME with your actual GitHub username)
git remote add origin https://github.com/YOUR-USERNAME/decision-graveyard-agent.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Example (if your username is "raghavendra"):**
```powershell
git remote add origin https://github.com/raghavendra/decision-graveyard-agent.git
git branch -M main
git push -u origin main
```

---

## Step 3: Add Topics (Tags) to Your Repo

On GitHub, go to your repo → click ⚙️ (Settings icon) next to "About" → Add topics:

```
ai
llm
hindsight
groq
fastapi
sse
semantic-search
decision-making
institutional-memory
hackathon
```

---

## Step 4: Update README with Your Repo URL

Replace this line in README.md:
```bash
git clone https://github.com/your-username/decision-graveyard
```

With:
```bash
git clone https://github.com/YOUR-ACTUAL-USERNAME/decision-graveyard-agent
```

Then commit and push:
```powershell
git add README.md
git commit -m "Update repo URL in README"
git push
```

---

## Step 5: Enable GitHub Actions (Optional)

GitHub Actions should auto-enable. Check:
1. Go to your repo
2. Click "Actions" tab
3. You should see the CI workflow ready to run

---

## Your Repo is Live! 🎉

Share this URL with hackathon judges:
```
https://github.com/YOUR-USERNAME/decision-graveyard-agent
```

---

## Important: Protect Your API Keys

✅ `.env` is already in `.gitignore` — your keys are safe
✅ `.env.example` shows structure without real keys
✅ README tells users to create their own `.env`

**Never commit your actual `.env` file!**
