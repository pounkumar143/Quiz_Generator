import streamlit as st
from openai import OpenAI
import pdfplumber
import docx
import pandas as pd
import time
import os

st.set_page_config(page_title="LLM Quiz App", layout="centered")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def extract_text(file):
    if file.name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "".join(page.extract_text() for page in pdf.pages if page.extract_text())
    elif file.name.endswith(".docx"):
        doc = docx.Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    else:
        return ""

def expand_topic(topic):
    prompt = f"Write a 300-word informative article about the topic: '{topic}'"
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

def generate_mcqs(context, n):
    prompt = f"""
Based on the following content, generate {n} multiple-choice questions.

Use this format:
Question: ...
A. ...
B. ...
C. ...
D. ...
Answer: ...
Explanation: ...

Content:
{context}
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

def parse_mcqs(raw_text):
    questions = []
    for block in raw_text.strip().split("\n\n"):
        if "Question:" in block:
            q_data = {"question": "", "options": [], "answer": "", "explanation": ""}
            lines = block.strip().split("\n")
            for line in lines:
                if line.lower().startswith("question"):
                    q_data["question"] = line.split(":", 1)[-1].strip()
                elif any(line.strip().startswith(opt) for opt in ["A.", "B.", "C.", "D."]):
                    q_data["options"].append(line.strip())
                elif line.lower().startswith("answer"):
                    q_data["answer"] = line.split(":", 1)[-1].strip()
                elif line.lower().startswith("explanation"):
                    q_data["explanation"] = line.split(":", 1)[-1].strip()
            if q_data["question"] and q_data["options"]:
                questions.append(q_data)
    return questions

# Leaderboard storage
LEADERBOARD_FILE = "leaderboard.csv"
if not os.path.exists(LEADERBOARD_FILE):
    pd.DataFrame(columns=["Name", "Email", "Topic", "Score", "Total"]).to_csv(LEADERBOARD_FILE, index=False)

# Login screen
if "started" not in st.session_state:
    st.session_state.started = False

if not st.session_state.started:
    st.title("🧑‍🎓 Welcome to the LLM Quiz App")
    name = st.text_input("Enter your name:")
    email = st.text_input("Enter your email:")
    topic = st.text_input("Enter a topic:")
    uploaded_file = st.file_uploader("Or upload a document", type=["pdf", "docx"])
    num_questions = st.slider("How many questions?", 1, 20, 5)

    if st.button("Start Quiz"):
        if not name or not email:
            st.warning("Name and email are required.")
        else:
            st.session_state.name = name
            st.session_state.email = email
            st.session_state.topic = topic
            st.session_state.uploaded_file = uploaded_file
            st.session_state.num_questions = num_questions
            st.session_state.started = True
            st.rerun()

# Quiz state
if st.session_state.started:
    if "quiz" not in st.session_state:
        context = ""
        if st.session_state.uploaded_file:
            context = extract_text(st.session_state.uploaded_file)
        elif st.session_state.topic:
            context = expand_topic(st.session_state.topic)
        raw = generate_mcqs(context, st.session_state.num_questions)
        st.session_state.quiz = parse_mcqs(raw)
        st.session_state.current = 0
        st.session_state.score = 0
        st.session_state.answers = []
        st.session_state.complete = False

    if st.session_state.current < len(st.session_state.quiz) and not st.session_state.complete:
        q = st.session_state.quiz[st.session_state.current]
        st.subheader(f"Q{st.session_state.current + 1}: {q['question']}")
        choice = st.radio("Choose an answer:", q["options"], key=st.session_state.current)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Submit Answer"):
                selected = choice.split(".")[0].strip()
                correct = q["answer"].strip().split(".")[0]
                is_correct = selected == correct
                st.session_state.answers.append({
                    "Question": q["question"],
                    "Your Answer": choice,
                    "Correct Answer": q["answer"],
                    "Explanation": q["explanation"],
                    "Result": "✅ Correct" if is_correct else "❌ Incorrect"
                })
                if is_correct:
                    st.session_state.score += 1
                st.session_state.current += 1
                time.sleep(3)
                st.rerun()
        with col2:
            if st.button("Complete Quiz"):
                st.session_state.complete = True
                st.rerun()

    if st.session_state.current >= len(st.session_state.quiz) or st.session_state.complete:
        st.success(f"🎉 Quiz Completed! You scored {st.session_state.score}/{len(st.session_state.quiz)}")
        df = pd.DataFrame(st.session_state.answers)
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results", data=csv, file_name="quiz_results.csv", mime="text/csv")

        # Save to leaderboard
        leaderboard_df = pd.read_csv(LEADERBOARD_FILE)
        new_entry = {
            "Name": st.session_state.name,
            "Email": st.session_state.email,
            "Topic": st.session_state.topic,
            "Score": st.session_state.score,
            "Total": len(st.session_state.quiz)
        }
        leaderboard_df = pd.concat([leaderboard_df, pd.DataFrame([new_entry])], ignore_index=True)
        leaderboard_df.to_csv(LEADERBOARD_FILE, index=False)

        st.subheader("🏆 Leaderboard (Top 10)")
        top_scores = leaderboard_df.sort_values(by="Score", ascending=False).head(10)
        st.dataframe(top_scores)
