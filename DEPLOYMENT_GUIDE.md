# Crop Disease Detection - Deployment Guide

## 📤 Pushing to GitHub

### Step 1: Create GitHub Repository
1. Go to [github.com](https://github.com) and log in
2. Click "+" → "New Repository"
3. Name: `crop-disease-ai`
4. Click "Create repository"
5. Copy the HTTPS URL shown (e.g., `https://github.com/YOUR_USERNAME/crop-disease-ai.git`)

### Step 2: Push Local Code to GitHub

Open **PowerShell** or **Command Prompt** in your project folder (`C:\Users\nikhi\Crop-Disease-Detection-for-Indian-Agriculture`):

```powershell
# Initialize git repository
git init

# Add GitHub as remote (replace with your actual URL)
git remote add origin https://github.com/YOUR_USERNAME/crop-disease-ai.git

# Add all project files
git add .

# Commit the code
git commit -m "Initial commit: Crop Disease Detection for Indian Agriculture"

# Push to GitHub (first time sets up tracking)
git push -u origin main
```

**Alternatively**, if your default branch is `main`:
```powershell
git push -u origin main
```

### Step 3: Connect Render to GitHub

1. Go to [render.com](https://render.com) and log in
2. New → Web Service (or Docker, depending on your choice)
3. Click "Connect a repository" → Select **GitHub**
4. Authorize Render to access your GitHub account
5. Select your repository: `crop-disease-ai`
6. Configure the service:
   - **Name**: `crop-disease-ai` (or your choice)
   - **Environment**: Docker (you have a Dockerfile already)
   - **Root Directory**: `.` (default)
   - **Dockerfile Path**: `Dockerfile` (auto-detected)

### Step 4: Set Environment Variables in Render

After the service is created, go to **Settings → Environment** and add all of these:

```
FLASK_SECRET_KEY=replace-with-a-random-secret-of-at-least-32-characters
DATABASE_URL=postgresql://postgres:password@internal-db-address:5432/crop_ai
DATA_GOV_IN_API_KEY=579b464db66ec23bdd000001a49705a12d4e41fb5a68da65d7e8f7e2
DATA_GOV_IN_MANDI_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
DATA_GOV_IN_BASE_URL=https://api.data.gov.in/resource
GEMINI_API_KEY=AQ.Ab8RN6Jr-UAJ6IF1wQikfs_SyFy23GQgoEnN6RqTiwgMz_4DOA
GEMINI_MODEL=gemini-3.6-flash
WEATHER_API_URL=https://api.openweathermap.org/data/2.5/forecast
WEATHER_API_KEY=655dbbf0ff1491deedcbec2ad444d070
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=nikhilkrsingh2004@gmail.com
SMTP_PASSWORD=Nikhil@123
SMTP_FROM=nikhilkrsingh2004@gmail.com
```

**Important**: You'll also need to add Render's PostgreSQL database:
- New → PostgreSQL on Render
- Note the internal address it gives you
- Use that in `DATABASE_URL` instead of localhost

### Step 5: Deploy

1. Click "Create Web Service" on Render
2. Watch the build log - it should:
   - Build your Docker image
   - Start PostgreSQL
   - Start your Flask API
3. Once ready, you'll get a URL like: `https://crop-disease-ai.onrender.com`

### Step 6: Share with Friends

Give them the Render URL! They can access all features:
- Crop scanning and disease detection
- Weather forecasts
- Farm records
- Market prices
- And all other features

---

## 🐳 Docker Deployment (Alternative)

Your project already has `Dockerfile` and `docker-compose.yml`, making Docker deployment straightforward:

1. Push code to GitHub (steps 1-3 above)
2. On Render: New → Docker instead of Web Service
3. Same environment variables as Step 4
4. Deploy and share the link

---

## 📋 Quick Reference - .env Values (from your local setup)

```
DATABASE_URL=postgresql://postgres:NIKHILSINGH100@localhost:5432/crop_ai
FLASK_SECRET_KEY=replace-with-a-random-secret-of-at-least-32-characters
DATA_GOV_IN_API_KEY=579b464db66ec23bdd000001a49705a12d4e41fb5a68da65d7e8f7e2
DATA_GOV_IN_MANDI_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
DATA_GOV_IN_BASE_URL=https://api.data.gov.in/resource
GEMINI_API_KEY=AQ.Ab8RN6Jr-UAJ6IF1wQikfs_SyFy23GQgoEnN6RqTiwgMz_4DOA
GEMINI_MODEL=gemini-3.6-flash
WEATHER_API_URL=https://api.openweathermap.org/data/2.5/forecast
WEATHER_API_KEY=655dbbf0ff1491deedcbec2ad444d070
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=nikhilkrsingh2004@gmail.com
SMTP_PASSWORD=Nikhil@123
SMTP_FROM=nikhilkrsingh2004@gmail.com
```

---

## ✅ What's Already Ready

- ✅ PostgreSQL running locally with all 10 migrations applied
- ✅ Frontend built with Vite/React (`frontend/dist/`)
- ✅ Flask backend running on `localhost:5000`
- ✅ `Dockerfile` exists in project root
- ✅ `docker-compose.yml` exists for local testing
- ✅ `.env` file configured with all API keys
- ✅ All API routes registered and functional

---

## 🔧 Need Help?

If you encounter issues:

**Git errors?** - I can help troubleshoot authentication or push problems
**Docker build failures?** - I can help fix build issues
**Environment variable errors?** - I can help configure the right values
**Database connection problems?** - I can help debug PostgreSQL connectivity

Just let me know what error you see, and I'll help you fix it!

---

*Generated from chat discussion on 2026-10-26*