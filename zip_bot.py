import tempfile
from os.path import basename
from zipfile import ZipFile
import os
from garnet import ctx
from garnet.runner import RuntimeConfig, run
from garnet.filters import text, State, group
from garnet.storages import DictStorage
from garnet.events import Router

# Bot credentials
BOT_TOKEN = "8064879322:AAH4Uv8ZJbHfDZRBnre_Uf4D-ew-Q8SCinc"
APP_ID = "27788368"  # Replace with your actual API ID
APP_HASH = "9df7e9ef3d7e4145270045e5e43e1081"
SESSION_DSN = "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"  # Optional, if using MongoDB for session storage

router = Router()

class States(group.Group):
    state_waiting = group.M()
    state_uploading = group.M()
    state_naming = group.M()

@router.use()
async def only_pm(handler, event):
    if event.is_private:
        try:
            return await handler(event)
        except Exception as e:
            print("Error happened", e)
            await event.reply(f"An error happened, please retry:\nError code: {e}")
            fsm = ctx.CageCtx.get()
            await fsm.set_state(States.state_waiting)
            await fsm.set_data({"files": []})

@router.message(text.commands("start", prefixes="/") & (State.exact(States.state_waiting) | State.entry))
async def response(event):
    await event.reply("Hi! Send me multiple files to zip.\nUse /done when you're ready to zip them.")
    fsm = ctx.CageCtx.get()
    await fsm.set_state(States.state_uploading)
    await fsm.set_data({"files": []})

@router.message(State.exact(States.state_waiting) | State.entry)
async def response(event):
    await event.reply("Send /start to begin.")

@router.message(text.commands("done", prefixes="/") & State.exact(States.state_uploading))
async def finished(event):
    fsm = ctx.CageCtx.get()
    await fsm.set_state(States.state_naming)
    await event.reply("Please enter a name for the ZIP file (without extension).")

@router.message(State.exact(States.state_naming))
async def naming(event):
    fsm = ctx.CageCtx.get()
    await fsm.set_state(States.state_waiting)
    data = await fsm.get_data()
    files = data['files']

    if not files:
        await event.reply("No files uploaded. Please send files first.")
        return

    msg = await event.reply("Processing ZIP file...")
    
    with tempfile.TemporaryDirectory() as tmp_dirname:
        zip_path = f"{tmp_dirname}/{event.text}.zip"
        with ZipFile(zip_path, 'w') as zipObj:
            for file in files:
                path = await event.client.download_media(file, file=tmp_dirname)
                zipObj.write(path, basename(path))
        
        await msg.edit(f"Zipping completed! Uploading file...")
        await event.reply(file=zip_path)

    await fsm.set_data({"files": []})

@router.message(State.exact(States.state_uploading))
async def uploading(event):
    if event.file:
        fsm = ctx.CageCtx.get()
        data = await fsm.get_data()
        files = data['files']
        files.append(event.message.media)
        await fsm.set_data(data)
        await event.reply(f"File saved! {len(files)} files added so far.")
    else:
        await event.reply("Please send a file or type /done when finished.")

def default_conf_maker() -> RuntimeConfig:
    return RuntimeConfig(
        bot_token=BOT_TOKEN,
        app_id=APP_ID,
        app_hash=APP_HASH,
        session_dsn=SESSION_DSN,
    )

async def main():
    main_router = Router().include(router)
    await run(main_router, DictStorage(), conf_maker=default_conf_maker)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
