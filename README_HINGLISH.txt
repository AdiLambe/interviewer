MOCK INTERVIEW - ANDROID APP (32 job roles, offline, no AI, no key)

Is folder mein app ka poora source hai. APK compile karne ke liye Android SDK + internet chahiye,
isliye GitHub ke free server par build karte hain (phone se bhi ho jaata hai).

A) GITHUB PAR APK BANANE KE STEPS (sirf phone browser se)
1. github.com par account banao (free) aur login karo.
2. New repository banao. Naam: mock-interview. Public rakho. "Create repository" dabao.
3. "uploading an existing file" / Add file > Upload files dabao.
   Is folder se ye 3 files chuno: main.py, interviewer.py, buildozer.spec. Commit changes dabao.
4. Add file > Create new file dabao.
   File name ki jagah ye likho (slash type karne se folder bante hain):
        .github/workflows/build-apk.yml
   Neeche box mein WORKFLOW_COPY_PASTE.txt ka poora text copy karke paste karo. Commit dabao.
5. Upar "Actions" tab kholo. "Build APK" > "Run workflow" dabao (ya commit ke baad apne aap chalega).
6. 20 se 35 minute ruko. Hara tick aaye to us run par tap karo.
   Neeche "Artifacts" mein "mock-interview-apk" download karo. Ye zip hai, extract karo.
7. Andar ki .apk file par tap karo. Phone "Install unknown apps" ki permission maange to allow karo.

Build fail ho to run kholo, laal step par tap karo, aur aakhri 30 lines ka screenshot bhej do.

B) LAPTOP (Ubuntu / WSL) PAR
   sudo apt update
   sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv build-essential autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
   python3 -m venv .venv && source .venv/bin/activate
   pip install --upgrade pip buildozer==1.5.0 "cython<3"
   buildozer android debug        (APK bin/ folder mein aata hai)

APP KAISE CHALTA HAI
- Role chuno (Playwright, Java, DevOps, Sales, Product, SAP ABAP, ... total 32) aur minutes likho.
- Sawaal phone ki awaaz mein bolta hai. Jawab type karo, ya keyboard ke mic key se bolke likho.
- REPEAT, HINT, SKIP, SUBMIT, END buttons hain. Aakhir mein score, strengths, gaps, study plan.
- Kisi AI ya API key ki zaroorat nahi. Sawaal interviewer.py mein hain, wahi file PC par bhi chalti hai.
