# EduReach Rwanda — Presentation Script
## 5-10 Minute Demo Video Guide

This script guides you through recording a professional 5-10 minute presentation video demonstrating EduReach Rwanda.

---

## Part 1: Introduction & Problem Statement (1-2 minutes)

**Script talking points:**

> "Hello, I'm [Your Name]. I'm presenting EduReach Rwanda, an offline learning hub designed for rural schools.
>
> **The Problem**: In Rwanda, while urban schools have internet and electricity, rural schools struggle. Only 12% of rural households have internet access, and only 54.2% of Rwandans have access to the national power grid. This creates a significant rural-urban education gap—students in rural areas can't access digital learning materials, and teachers can't distribute curriculum-aligned content.
>
> **Why This Matters**: Education is the foundation for economic development. When students in rural areas lack access to learning resources, they fall behind, perpetuating inequality.
>
> **The Solution**: EduReach Rwanda is an offline-first learning hub. Teachers upload lessons and quizzes to a local device at school. Students then access this content completely offline over the school's Wi-Fi network, with no internet required. Quiz results are marked automatically and stored locally, ready to sync when connectivity returns."

**Visual aids to show during this section:**
- Show the EduReach Rwanda login page on screen
- Display the README.md file from the GitHub repo showing the problem statement

---

## Part 2: Key Features Demo (3-5 minutes)

### 2a. Student Journey (2-3 min)

**Demo steps:**

1. **Show Login Page** (10 seconds)
   - Point out "Learning that works without internet" tagline
   - Show username/password fields
   - Mention demo accounts

2. **Login as Student** (1 minute 30 seconds)
   - Username: `student`
   - Password: `1234`
   - Say: "Now I'm logged in as Ishimwe, a P6 student. Notice the interface is clean and minimal—no heavy animations or web fonts to drain battery on a low-power device."
   - Show the lesson dashboard with filters by subject and grade
   - Demonstrate searching/filtering lessons

3. **Open a Lesson** (1 minute)
   - Click on "Fractions: adding and subtracting" (Mathematics, P6)
   - Say: "Teachers create lessons with supporting materials—notes, PDFs, images, or videos. All stored locally. All accessible without internet."
   - Scroll through the lesson content
   - Point out the lesson is fully readable

4. **Take and Complete a Quiz** (1 minute 30 seconds)
   - Click "Take quiz: Fractions quiz"
   - Say: "One of the most important features—students can take quizzes and get instant feedback, all offline."
   - Answer 2-3 questions visibly (pick the correct answers)
   - Click "Submit"
   - Point out: "The quiz is instantly auto-graded. The student sees their score, correct answers, and can review immediately. No waiting for a teacher to mark. This encourages learning."

### 2b. Teacher Functionality (1-2 min)

5. **Logout and Login as Teacher**
   - Logout (click button)
   - Login with `teacher` / `teach123`
   - Say: "Now let's look from the teacher's perspective. Teachers can upload lessons, create quizzes with answer keys, and monitor student progress."

6. **Show Teacher Dashboard**
   - Highlight "My lessons" section with the 3 lessons
   - Point out: upload new lesson, edit, manage quizzes, remove lessons
   - Say: "Teachers maintain their own content. They can't see or modify other teachers' lessons—data integrity is important in an offline environment."

7. **Show Class Progress**
   - Navigate to "Class progress"
   - Say: "Teachers can see which students have completed quizzes, their scores, and class averages. The 'PENDING' status means results are ready to sync to the central server when connectivity returns."
   - Show the latest results table with student scores

---

## Part 3: Technical Implementation (1-2 minutes)

**Script talking points:**

> "Let me show you a bit about how this works technically.
>
> **Stack**: Python Flask, SQLite database, server-rendered HTML. No heavy JavaScript frameworks. No web fonts or animations. This design choice is intentional—it minimizes battery drain and data usage.
>
> **Offline-First**: The entire application works without internet. Database and files are stored locally. Students and teachers can work completely offline.
>
> **Data Safety**: We use SQLite Write-Ahead Logging and synchronous writes to protect data even if power fails mid-operation.
>
> **Planned Sync**: Quiz results and progress are marked 'PENDING' until they sync to the central server when connectivity returns. This allows the hub to operate independently while still connecting to central systems when possible.
>
> **Testing**: The system has been tested with realistic scenarios—no internet, unreliable power, low-spec devices. 20 test cases cover login, roles, lesson uploads, quizzes, progress tracking, and power safety."

**Visual aids:**
- Show the README.md "What works now" table
- Show the GitHub repo structure
- Mention the test coverage

---

## Part 4: Deployment & Live Access (1 minute)

**Script talking points:**

> "EduReach Rwanda has been deployed to a public URL: [INSERT PUBLIC URL HERE AFTER DEPLOYMENT]
>
> You can test it right now by visiting that link, logging in with the demo credentials, and exploring the system yourself.
>
> The source code is fully open on GitHub: https://github.com/nshutilancelot3/edureach-rwanda
>
> The development process followed agile practices—feature branches, pull requests, and regular commits across the project timeline. The git history shows steady progress from initial setup through the first complete increment."

---

## Part 5: Closing (30 seconds)

**Script talking points:**

> "EduReach Rwanda is increment 1 of a broader vision to bring offline-first learning to rural schools across Rwanda. It demonstrates that quality education tools don't need heavy cloud infrastructure—they can run reliably on a single low-cost device serving an entire school.
>
> The system is currently being prepared for real-world testing in rural classrooms. Future increments will add features like multilingual content, advanced reporting, and integration with the central sync server.
>
> Thank you."

---

## Recording Tips

1. **Screen Resolution**: Record at 1920x1080 for clarity
2. **Narration**: Speak clearly, slowly, and confidently. Pause between sections.
3. **Demo Pacing**: Let each demo step linger for 3-5 seconds so viewers can read and understand
4. **Keyboard/Mouse**: Make clicks and navigation visible and intentional
5. **Audio**: Use a good microphone and minimize background noise
6. **Final Length**: Aim for 5-10 minutes total. This script guides you to roughly 7-8 minutes.

---

## Total Demo Flow

| Section | Duration | Focus |
|---------|----------|-------|
| Intro & Problem | 1-2 min | Context, why EduReach matters |
| Student Demo | 2-3 min | Login, lessons, quiz, auto-marking |
| Teacher Demo | 1-2 min | Dashboard, progress tracking |
| Technical | 1-2 min | Stack, offline design, testing |
| Deployment | 1 min | Live URL, GitHub repo, agile process |
| Closing | 0.5 min | Vision and impact |
| **Total** | **7-10 min** | Rubric compliant |

---

## Important: Don't Forget to Insert the Live URL!

Before submitting:
1. Deploy EduReach Rwanda to a public URL using the DEPLOYMENT.md guide
2. Test it works at that URL
3. Update "INSERT PUBLIC URL HERE AFTER DEPLOYMENT" in this script
4. Include that URL in your presentation video's closing

**Example public URLs after deployment:**
- Railway: `https://edureach-*.railway.app`
- Render: `https://edureach-*.onrender.com`
- PythonAnywhere: `https://<username>.pythonanywhere.com`
