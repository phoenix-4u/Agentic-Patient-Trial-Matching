from agno.agent import Agent
from agno.models.azure import AzureOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

os.environ["AZURE_OPENAI_API_KEY"] = os.getenv("AZURE_OPENAI_API_KEY")
os.environ["AZURE_OPENAI_ENDPOINT"] = os.getenv("AZURE_OPENAI_ENDPOINT")
os.environ["AZURE_OPENAI_API_TYPE"] = os.getenv("AZURE_OPENAI_API_TYPE")
os.environ["OPENAI_API_Version"] = os.getenv("OPENAI_API_Version")

agent = Agent(
    model=AzureOpenAI(id=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")),
    markdown=True
)

# Print the response on the terminal
agent.print_response("Share a 2 sentence horror story.")
