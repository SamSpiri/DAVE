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

app_config_toml = toml.load(".streamlit/app.toml")

if app_config_toml["global"]["require_password"] and not check_password():
    st.stop()  # Do not continue if check_password is not True.


dbs = app_config_toml['databases']
if "database" not in st.session_state:
    st.selectbox('Select Database', dbs.keys(), index=None, placeholder="Please Select", key="database_select")
    for db in dbs.keys():
        st.markdown(app_config_toml['databases'][db]["description"])
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

    # Local history
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.markdown(app_config["welcome_message"])

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

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):

            # Create a new thread
            if "thread_id" not in st.session_state:
                thread = client.beta.threads.create()
                st.session_state.thread_id = thread.id

            client.beta.threads.update(
                    thread_id=st.session_state.thread_id,
            )
            client.beta.threads.messages.create(
                thread_id=st.session_state.thread_id,
                role="user",
                content=f"{app_config['pre_prompt']}{prompt}"
            )

            stream = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=ASSISTANT_ID,
                stream=True
            )

            def stream_generator():
                assistant_output = ""

                for event in stream:
                    if isinstance(event, ThreadMessageCreated):
                        assistant_output = ""

                    elif isinstance(event, ThreadMessageDelta):
                        delta = event.data.delta.content[0]
                        if isinstance(delta, TextDeltaBlock):
                            new_text = ""
                            annotations = delta.text.annotations
                            if annotations is not None and len(annotations):
                                for annotation in annotations:
                                    new_text += f" [{annotation.index+1}] "
                            else:
                                new_text = delta.text.value
                            assistant_output += new_text
                            yield new_text

                    elif isinstance(event, ThreadMessageCompleted):
                        annotations = event.data.content[0].text.annotations
                        if annotations is not None and len(annotations):
                            assistant_output += f"\n\nFiles: "
                            index = 0
                            for annotation in annotations:
                                index += 1
                                if file_citation := getattr(annotation, "file_citation", None):
                                    cited_file = client.files.retrieve(file_citation.file_id)
                                    assistant_output += f"[{index}] {cited_file.filename}; "
                            yield assistant_output[len(assistant_output) - len(new_text):]

                    elif isinstance(event, ThreadRunStepCompleted) and app_config_toml["global"]["print_usage"]:
                        if event.data.usage is not None:
                            usage_info = f"{event.data.usage}"
                            yield usage_info

                        st.rerun()

                st.session_state.messages.append({"role": "assistant", "items": [{"type": "text", "content": assistant_output}]})

            st.write_stream(stream_generator())
