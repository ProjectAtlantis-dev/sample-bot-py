## Botty

Standalone chat interface to exercise Poe and Atlantis protocols


To run:

`git clone https://github.com/smol-ai/developer`
`cd botty`

Get your OPENAI API key here https://platform.openai.com/account/api-keys

To test Poe, head over to https://poe.com/ and create a bot and get the API key

You will also need to specify the bot URL. Assuming we will use port 8000, run something like ngrok
https://ngrok.com/download

`ngrok http 8000`

Then copy and paste the assigned API into the Poe bot URL


Now let's run the actual bot server

On your computer, set POE_API_KEY and launch uvicorn (in the botty/botty subfolder) on port 8000:
`run runMe`

This will check memory/config.json for an existing OPENAI API KEY. If not found then will prompt for one


