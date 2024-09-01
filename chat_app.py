"""
chat_app.py
"""
import base64
import os
import hmac
import streamlit as st
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
        if hmac.compare_digest(st.session_state["password"], st.secrets["password"]):
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


if not check_password():
    st.stop()  # Do not continue if check_password is not True.

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

# Get secrets
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
ASSISTANT_ID = st.secrets["ASSISTANT_ID"]

# Initialise the OpenAI client, and retrieve the assistant
client = OpenAI(api_key=OPENAI_API_KEY)
assistant = client.beta.assistants.retrieve(ASSISTANT_ID)

# Apply custom CSS
st.html("""
        <style>
            #MainMenu {visibility: hidden}
            #header {visibility: hidden}
            #footer {visibility: hidden}
            .block-container {
                padding-top: 3rem;
                padding-bottom: 2rem;
                padding-left: 3rem;
                padding-right: 3rem;
                }
        </style>
        """)

# Initialise session state
for session_state_var in ["file_uploaded"]:
    if session_state_var not in st.session_state:
        st.session_state[session_state_var] = False

# Moderation check
def moderation_endpoint(text) -> bool:
    """
    Checks if the text is triggers the moderation endpoint

    Args:
    - text (str): The text to check

    Returns:
    - bool: True if the text is flagged
    """
    response = client.moderations.create(input=text)
    return response.results[0].flagged

# UI
st.subheader("🔮 Ask a question to Shrila Prabhupada's books.")

# add page reload button:
if st.button("♻️ New chat"):
    st.session_state.clear()
    st.rerun()

file_upload_box = st.empty()
upload_btn = st.empty()

# # Upload a file
# # File Upload
# if not st.session_state["file_uploaded"]:
#     st.session_state["files"] = file_upload_box.file_uploader("Please upload your dataset(s)",
#                                                               accept_multiple_files=True,
#                                                               type=["csv"])
#
#     if upload_btn.button("Upload"):
#
#         st.session_state["file_id"] = []
#
#         # Upload the file
#         for file in st.session_state["files"]:
#             oai_file = client.files.create(
#                 file=file,
#                 purpose='assistants'
#             )
#
#             # Append the file ID to the list
#             st.session_state["file_id"].append(oai_file.id)
#             print(f"Uploaded new file: \t {oai_file.id}")
#
#         st.toast("File(s) uploaded successfully", icon="🚀")
#         st.session_state["file_uploaded"] = True
#         file_upload_box.empty()
#         upload_btn.empty()
#         # The re-run is to trigger the next section of the code
#         st.rerun()

if st.session_state["file_uploaded"] or True:

    # Create a new thread
    if "thread_id" not in st.session_state:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        print(st.session_state.thread_id)

    # Update the thread to attach the file
    client.beta.threads.update(
            thread_id=st.session_state.thread_id,
            #tool_resources={"code_interpreter": {"file_ids": [file_id for file_id in st.session_state.file_id]}}
            )

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

    if prompt := st.chat_input("Describe your query in detail. There will be no clarifying questions."):
        #if moderation_endpoint(prompt):
        #    st.toast("Your message was flagged. Please try again.", icon="⚠️")
        #    st.stop

        st.session_state.messages.append({"role": "user",
                                        "items": [
                                            {"type": "text", 
                                            "content": prompt
                                            }]})
        
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=f"Используй файлы и приводи полные цитаты: {prompt}"
        )

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            stream = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=ASSISTANT_ID,
                #tool_choice={"type": "code_interpreter"},
                stream=True
            )

            assistant_output = []

            for event in stream:
                print(event)
#                 if isinstance(event, ThreadRunStepCreated):
#                     if event.data.step_details.type == "tool_calls":
#                         assistant_output.append({"type": "code_input",
#                                                 "content": ""})
#
#                         code_input_expander= st.status("Writing code ⏳ ...", expanded=True)
#                         code_input_block = code_input_expander.empty()
#
#                 if isinstance(event, ThreadRunStepDelta):
#                     if event.data.delta.step_details.tool_calls[0].code_interpreter is not None:
#                         code_interpretor = event.data.delta.step_details.tool_calls[0].code_interpreter
#                         code_input_delta = code_interpretor.input
#                         if (code_input_delta is not None) and (code_input_delta != ""):
#                             assistant_output[-1]["content"] += code_input_delta
#                             code_input_block.empty()
#                             code_input_block.code(assistant_output[-1]["content"])
#
#                 elif isinstance(event, ThreadRunStepCompleted):
#                     if isinstance(event.data.step_details, ToolCallsStepDetails):
#                         code_interpretor = event.data.step_details.tool_calls[0].code_interpreter
#                         if code_interpretor.outputs is not None:
#                             code_interpretor_outputs = code_interpretor.outputs[0]
#                             code_input_expander.update(label="Code", state="complete", expanded=False)
#                             # Image
#                             if isinstance(code_interpretor_outputs, CodeInterpreterOutputImage):
#                                 image_html_list = []
#                                 for output in code_interpretor.outputs:
#                                     image_file_id = output.image.file_id
#                                     image_data = client.files.content(image_file_id)
#
#                                     # Save file
#                                     image_data_bytes = image_data.read()
#                                     with open(f"images/{image_file_id}.png", "wb") as file:
#                                         file.write(image_data_bytes)
#
#                                     # Open file and encode as data
#                                     file_ = open(f"images/{image_file_id}.png", "rb")
#                                     contents = file_.read()
#                                     data_url = base64.b64encode(contents).decode("utf-8")
#                                     file_.close()
#
#                                     # Display image
#                                     image_html = f'<p align="center"><img src="data:image/png;base64,{data_url}" width=600></p>'
#                                     st.html(image_html)
#
#                                     image_html_list.append(image_html)
#
#                                 assistant_output.append({"type": "image",
#                                                         "content": image_html_list})
#                             # Console log
#                             elif isinstance(code_interpretor_outputs, CodeInterpreterOutputLogs):
#                                 assistant_output.append({"type": "code_output",
#                                                          "content": ""})
#                                 code_output = code_interpretor.outputs[0].logs
#                                 with st.status("Results", state="complete"):
#                                     st.code(code_output)
#                                     assistant_output[-1]["content"] = code_output
#
#                elif isinstance(event, ThreadMessageCreated):
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
                        assistant_output[-1]["content"] += f"\n\nFiles:\n"
                        index = 0
                        for annotation in annotations:
                            index += 1
                            #message_content.value = message_content.value.replace(
                            #    annotation.text, f"[{index}]"
                            #)
                            if file_citation := getattr(annotation, "file_citation", None):
                                cited_file = client.files.retrieve(file_citation.file_id)
                                assistant_output[-1]["content"] += f"- [{index}] {cited_file.filename}\n"
                                assistant_text_box.markdown(assistant_output[-1]["content"])

                elif isinstance(event, ThreadRunStepCompleted):
                    if event.data.usage is not None:
                        assistant_text_box = st.empty()
                        assistant_output.append({"type": "text",
                                                "content": f"{event.data.usage}"})
                        assistant_text_box.markdown(assistant_output[-1]["content"])

            st.session_state.messages.append({"role": "assistant", "items": assistant_output})

# ThreadMessageCompleted(data=Message(id='msg_iBHSNLIkwEkAmc4jtOsXciMJ', assistant_id='asst_Mur6zlOfYl9kwmc9EYJHud2p', attachments=[], completed_at=1725141840,
#content=[TextContentBlock(text=Text(annotations=[FileCitationAnnotation(end_index=389, file_citation=FileCitation(file_id='file-4YD0SwCRVMU9YoUvogd6Pnnu',
# quote=None), start_index=376, text='【4:15†source】', type='file_citation'), FileCitationAnnotation(end_index=746,
# file_citation=FileCitation(file_id='file-sWzPeWCMdrqlrcMyd4NGMw29', quote=None), start_index=734, text='【4:7†source】', type='file_citation'),
#  FileCitationAnnotation(end_index=1135, file_citation=FileCitation(file_id='file-MO1yxNzQqxIAuRLdEROFfQV6', quote=None), start_index=1123, text='【4:1†source】',
#   type='file_citation'), FileCitationAnnotation(end_index=1419, file_citation=FileCitation(file_id='file-4YD0SwCRVMU9YoUvogd6Pnnu', quote=None),
#   start_index=1407, text='【4:4†source】', type='file_citation'), FileCitationAnnotation(end_index=1766,
#   file_citation=FileCitation(file_id='file-MO1yxNzQqxIAuRLdEROFfQV6', quote=None), start_index=1754, text='【4:1†source】', type='file_citation'),
#    FileCitationAnnotation(end_index=2014, file_citation=FileCitation(file_id='file-9AoM6vyBUjsxV6kvOKDnym5s', quote=None),
#    start_index=2001, text='【4:16†source】', type='file_citation')],
#    value='Чтобы научиться предсказывать будущее, важно понимать несколько ключевых аспектов, основанных на ведическом знании и учениях Шрилы Прабхупады.\n\n1. **Знание о времени и карме**: Веды учат, что наше будущее зависит от наших действий в прошлом и настоящем. Как сказано в «Шримад-Бхагаватам», "в зависимости от степени осквернения тремя гунами человек пребывает в трех состояниях"【4:15†source】. Это означает, что наше поведение и поступки формируют нашу судьбу.\n\n2. **Астрология как инструмент**: Астрология — это один из способов предсказания будущего, который использует расположение небесных тел. В «Шримад-Бхагаватам» упоминается, что "производя расчеты, связанные с расположением светил, можно предсказать, что ожидает нас в будущем"【4:7†source】. Астрологи могут использовать свои знания, чтобы определить, какие события могут произойти в жизни человека, основываясь на его гороскопе.\n\n3. **Духовная практика**: Освобожденные души, такие как великий мудрец Вьясадева, могут предсказывать будущее благодаря своей духовной проницательности, которая достигается через практику преданного служения и изучение священных писаний【4:1†source】. Это подчеркивает важность духовного роста и практики в понимании будущего.\n\n4. **Понимание природы времени**: Веды учат, что время осквернено тремя гунами (благостью, страстью и невежеством), и наше восприятие времени и событий зависит от того, в какой гуне мы находимся【4:4†source】. Осознание этого может помочь нам лучше понять, как наши действия влияют на наше будущее.\n\n5. **Служение и сострадание**: Истинные преданные, такие как Шрила Прабхупада, стремятся служить другим и помогать им. Это служение не только приносит благо другим, но и очищает душу, позволяя лучше понимать свою судьбу и предсказывать будущее【4:1†source】.\n\n6. **Смирение и преданность**: Важно помнить, что предсказание будущего — это не просто механический процесс. Оно требует смирения и преданности Богу. Как говорит Господь Кришна в «Бхагавад-гите», "Мой преданный никогда не погибнет"【4:16†source】. Это подчеркивает, что преданность и служение Богу могут привести к лучшему пониманию своей судьбы.\n\nТаким образом, чтобы научиться предсказывать будущее, необходимо сочетать знание о карме, изучение астрологии, духовную практику, понимание времени и служение другим. Это путь, который требует времени и усилий, но он ведет к глубокому пониманию жизни и своего места в ней.'),
#     type='text')], created_at=1725141828, incomplete_at=None, incomplete_details=None, metadata={}, object='thread.message',
#     role='assistant', run_id='run_wpP8tkSdWrQTbpCeIfJ2Qogm', status='completed', thread_id='thread_2c7IG9eGLIJfJWNlmXDEKnSr'), event='thread.message.completed')



