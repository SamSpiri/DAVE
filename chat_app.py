"""
chat_app.py
"""

import streamlit as st

import base64
import os
import hmac
import toml

from openai import OpenAI
from openai.types.beta.assistant_stream_event import (
    ThreadRunStepCreated,
    ThreadRunStepDelta,
    ThreadRunStepCompleted,
    ThreadMessageCreated,
    ThreadMessageDelta,
    ThreadMessageCompleted
    )
from openai.types.beta.threads.text_delta_block import TextDeltaBlock 
from openai.types.beta.threads.runs.tool_calls_step_details import ToolCallsStepDetails
from openai.types.beta.threads.runs.code_interpreter_tool_call import (
    CodeInterpreterOutputImage,
    CodeInterpreterOutputLogs
    )



def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if hmac.compare_digest(st.session_state["password"], st.secrets["global"]["password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store the password.
        else:
            st.session_state["password_correct"] = False

    # Return True if the password is validated.
    if st.session_state.get("password_correct", False):
        return True

    # Show input for password.
    st.text_input(
        "Password", type="password", on_change=password_entered, key="password"
    )
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect")
    return False


# Set page config
st.set_page_config(page_title="Vedic GPT Chat",
                   layout='wide')

st.markdown("""
    <style>
        .reportview-container {
            margin-top: -2em;
        }
        #MainMenu {visibility: hidden;}
        .stDeployButton {display:none;}
        footer {visibility: hidden;}
        #stDecoration {display:none;}
    </style>
""", unsafe_allow_html=True)

#if not check_password():
#    st.stop()  # Do not continue if check_password is not True.


app_config_toml = toml.load(".streamlit/app.toml")
dbs = app_config_toml['databases']
if "database" not in st.session_state:
    st.selectbox('Select Database', dbs.keys(), index=None, placeholder="Please Select", key="database_select")
    if st.session_state["database_select"] is None:
        st.stop()
    st.session_state["database"] = st.session_state["database_select"]
    st.rerun()
database = st.session_state["database"]
app_config = dbs[database]

# Apply custom CSS
st.html("""
        <style>
            #MainMenu {visibility: hidden}
            header[data-testid="stHeader"] {
                background-color: transparent;
            }
            #footer {visibility: hidden}
            .block-container {
                padding-top: 0;
                }
        </style>
        """)

if False:
    col1, col2, col3 = st.columns([2,1,1])
    with col1:
        st.subheader(app_config["subtitle"])
    with col2:
        # add page reload button:
        if st.button(app_config["new_chat"]):
            database = st.session_state["database"]
            st.session_state.clear()
            st.session_state["database"] = database
            st.rerun()
    with col3:
        if st.button("Change Database"):
            st.session_state.clear()
            st.rerun()
else:
    st.subheader(app_config["subtitle"])

if True:

# но это тестовый запрос, проигнорируй


    # Local history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # UI
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            for item in message["items"]:
                item_type = item["type"]
                if item_type == "text":
                    st.markdown(item["content"])
                elif item_type == "image":
                    for image in item["content"]:
                        st.html(image)
                elif item_type == "code_input":
                    with st.status("Code", state="complete"):
                        st.code(item["content"])
                elif item_type == "code_output":
                    with st.status("Results", state="complete"):
                        st.code(item["content"])

    if prompt := st.chat_input(app_config["prompt"]):

        #st.write("dialog placeholder")
        #st.stop()

        # Get secrets
        OPENAI_API_KEY = st.secrets[database]["OPENAI_API_KEY"]
        ASSISTANT_ID = st.secrets[database]["ASSISTANT_ID"]

        # Initialise the OpenAI client, and retrieve the assistant
        client = OpenAI(api_key=OPENAI_API_KEY)
        assistant = client.beta.assistants.retrieve(ASSISTANT_ID)

        st.session_state.messages.append({"role": "user",
                                        "items": [
                                            {"type": "text", 
                                            "content": prompt
                                            }]})

        # Create a new thread
        if "thread_id" not in st.session_state:
            thread = client.beta.threads.create()
            st.session_state.thread_id = thread.id
            print(st.session_state.thread_id)

        client.beta.threads.update(
                thread_id=st.session_state.thread_id,
        )
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=f"{app_config['pre_prompt']}{prompt}"
        )

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            stream = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=ASSISTANT_ID,
                stream=True
            )

            assistant_output = []

            for event in stream:
                print(event)
                if isinstance(event, ThreadMessageCreated):
                    assistant_output.append({"type": "text",
                                            "content": ""})
                    assistant_text_box = st.empty()

                elif isinstance(event, ThreadMessageDelta):
                    delta = event.data.delta.content[0]
                    if isinstance(delta, TextDeltaBlock):
                        assistant_text_box.empty()
                        annotations = delta.text.annotations
                        if annotations is not None and len(annotations):
                            for annotation in annotations:
                                assistant_output[-1]["content"] += f" [{annotation.index+1}] "
                        else:
                            assistant_output[-1]["content"] += delta.text.value
                        assistant_text_box.markdown(assistant_output[-1]["content"])

                elif isinstance(event, ThreadMessageCompleted):
                    annotations = event.data.content[0].text.annotations
                    if annotations is not None and len(annotations):
                        assistant_output[-1]["content"] += f"\n\nFiles: "
                        index = 0
                        for annotation in annotations:
                            index += 1
                            if file_citation := getattr(annotation, "file_citation", None):
                                cited_file = client.files.retrieve(file_citation.file_id)
                                assistant_output[-1]["content"] += f"[{index}] {cited_file.filename}; "
                                assistant_text_box.markdown(assistant_output[-1]["content"])

                elif isinstance(event, ThreadRunStepCompleted) and app_config.print_usage:
                    if event.data.usage is not None:
                        assistant_text_box = st.empty()
                        assistant_output.append({"type": "text",
                                                "content": f"{event.data.usage}"})
                        assistant_text_box.markdown(assistant_output[-1]["content"])

            st.session_state.messages.append({"role": "assistant", "items": assistant_output})
