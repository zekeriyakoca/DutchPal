# frontend.py
import streamlit as st
import requests

st.title("🇳🇱 Dutch Language Assistant")
st.write("Ask anything about Dutch grammar, translations, or lessons!")

query = st.text_input("Your question:", placeholder="e.g., Translate 'Ik hou van jou'")

if st.button("Ask"):
    if query:
        with st.spinner("Asking the assistant..."):
            response = requests.post(
                "http://localhost:40001/ask",
                json={"message": query, "page": "sentences"},
            )
            if response.ok:
                st.markdown(response.json()["response"])
            else:
                st.error("Something went wrong.")
