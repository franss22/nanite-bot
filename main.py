import functools
import json
import io
import nextcord
from nextcord.ext import commands, menus
from nextcord.utils import get as nextcord_get
from nextcord.ext.commands import Context as Ctx
import nextcord.ext.application_checks
from nextcord.ui import Button
import redis
import os
from data import database, CLASSES
from data import DatabaseMissingValueException as DBNone

class CharacterNotFoundException(Exception):
    pass

intents = nextcord.Intents.default()
intents.message_content = True

conn= redis.StrictRedis.from_url(os.environ.get("REDIS_URL"))
DEBUG=True

db = database(conn)

bot = commands.Bot(command_prefix=")", intents=intents)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')


async def is_servicio_tecnico(ctx:Ctx):
    role = nextcord_get(ctx.guild.roles, name="Servicio tecnico")
    return role in ctx.author.roles


class Register(menus.ButtonMenu):
    def __init__(self, user_id, pc_name, floor):
        super().__init__(disable_buttons_after=True)
        for key, name in CLASSES.items():
            async def CB(itrx:nextcord.Interaction, k=key, n=name):
                db.register(user_id, pc_name, floor, k)
                await itrx.send(f"Personaje registrado con clase {n}!")
                self.stop()
            butt = Button(label=name)
            butt.callback = CB
            self.add_item(butt)
    async def send_initial_message(self, ctx, channel):
        return await channel.send(f'Selecciona la clase de tu PJ.', view=self)


@bot.command()
async def register(ctx:Ctx, nombre:str, piso:int):
    user_id = ctx.author.id
    try:
        pc_name = db.get_pc_name(user_id)
        await ctx.send(f"Ya tienes el PJ {pc_name} asignado. Si quieres registrar un nuevo PJ, elimina el anterior primero.")
        return
    except DBNone:
        await Register(user_id, nombre, piso).start(ctx)
        

def get_pc_data_from_user_id(user_id):
    try:
        pc_name = db.get_pc_name(user_id)
        return db.get_pc(user_id, pc_name)
    except DBNone as e:
        raise CharacterNotFoundException(str(e))

def gets_character(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if DEBUG:
            return await func(*args, **kwargs)
        else:
            try:
                return await func(*args, **kwargs)
            except CharacterNotFoundException:
                ctx:Ctx = args[0]
                await ctx.send("Error: no tienes un PJ registrado")
            except DBNone as e:
                ctx:Ctx = args[0]
                await ctx.send(f"Error, {str(e)}")
    return wrapper



@bot.command()
@gets_character
async def status(ctx:Ctx):
    pc_data = get_pc_data_from_user_id(ctx.author.id)
    name= pc_data["name"]
    floor= pc_data["floor"]
    credits= pc_data["credits"]
    dt= pc_data["dt"]
    classes= pc_data["classes"]
    class_names= [CLASSES[key] for key in classes]
    class_string= ", ".join(class_names)
    message=f"""## Status de {name}
- **Piso:** {floor}
- **Credits:** {credits}
- **Downtime:** {dt} dias
- **Clase{"s" if len(classes)>1 else ""}:** {class_string}"""
    await ctx.send(message)

@bot.command()
@gets_character
async def creds(ctx:Ctx, delta:int=0):
    user_id = ctx.author.id
    pc_name = db.get_pc_name(user_id)
    success, old, updated = db.update_int_val(user_id, pc_name, "credits", delta)
    if delta==0:
        message=f"`Créditos de {pc_name}:` {updated}"
    elif success:
        message=f"""`Créditos de {pc_name} actualizado:` {old} -> {updated} ({'+' if delta>0 else ''}{delta})"""
    else:
        message=f"{pc_name} no tiene suficientes créditos para esta operación ({old})"
    await ctx.send(message)

@bot.command()
@gets_character
async def dt(ctx:Ctx, delta:int=0):
    user_id = ctx.author.id
    pc_name = db.get_pc_name(user_id)
    success, old, updated = db.update_int_val(user_id, pc_name, "dt", delta)
    if delta==0:
        message=f"`Dowtime de {pc_name}:` {updated}"
    elif success:
        message=f"""`Downtime de {pc_name} actualizado:` {old} -> {updated} ({'+' if delta>0 else ''}{delta})"""
    else:
        message=f"{pc_name} no tiene suficiente donwtime para esta operación ({old})"
    await ctx.send(message)

@bot.command()
@commands.check(is_servicio_tecnico)
async def reset_dt(ctx:Ctx, dt:int):
    users = db.user_list()
    i = 0
    for user in users:
        user_id = user.decode("utf-8")
        pc_name = db.get_pc_name(user_id)
        db.replace_val(user_id, pc_name, "dt", dt)
        i+=1

    await ctx.send(f"Cambiado el dt de {i} PJs.")

@bot.command()
@commands.check(is_servicio_tecnico)
async def backup(ctx:Ctx):
    users = db.user_list()
    txt = ""
    for user in users:
        data = get_pc_data_from_user_id(user.decode("utf-8"))
        txt+=user.decode("utf-8")+"\t"+json.dumps(data)+"\n"

    await ctx.send("Backup completado", file=nextcord.File(fp=io.BytesIO(txt.encode("utf-8")), filename="backup.txt"))

@bot.command()
@gets_character
async def piso(ctx:Ctx, new_floor:int):
    user_id = ctx.author.id
    pc_name = db.get_pc_name(user_id)
    success, old, updated = db.update_int_val(user_id, pc_name, "credits", new_floor, replace=True, can_go_negative=True)
    if success:
        message=f"""`{pc_name} se mueve de piso:` {old} -> {updated}"""
    else:
        message=f"Hubo un error cambiando a {pc_name} de piso. Esto no debiera pasar, llame a Pancho pls."
    await ctx.send(message)

class UpdateClasses(menus.ButtonMenu):
    def __init__(self, user_id, pc_name, add=True):
        self.add = add
        super().__init__(disable_buttons_after=True)
        pc_data = db.get_pc(user_id, pc_name)
        classes = pc_data["classes"]
        self.not_enough_classes=(classes==1 and not add)

        if self.not_enough_classes:
            return
        if add:
            class_options = [item for item in CLASSES.keys() if item not in classes]
        else:
            class_options = classes

        for class_key in class_options:
            class_name = CLASSES[class_key]
            cc = classes.copy()
            cc.append(class_key) if add else cc.remove(class_key)
            async def CB(itrx:nextcord.Interaction, n=class_name, c=cc):
                db.replace_val(user_id, pc_name, "classes", c)
                await itrx.send(f'Clase {n} {"añadida" if self.add else "quitada"}')
                self.stop()
            butt = Button(label=class_name)
            butt.callback = CB
            self.add_item(butt)
    async def send_initial_message(self, ctx, channel):
        if self.not_enough_classes:
            return await channel.send(f'No puedes eliminar tu única clase. Añade otra clase primero.', view=self)
        return await channel.send(f'Selecciona la clase que quieres {"añadir" if self.add else "quitar"}.', view=self)
    
@bot.command()
@gets_character
async def añadir_clase(ctx:Ctx):
    user_id = ctx.author.id
    pc_name = db.get_pc_name(user_id)
    await UpdateClasses(user_id, pc_name, add=True).start(ctx)
    
@bot.command()
@gets_character
async def quitar_clase(ctx:Ctx):
    user_id = ctx.author.id
    pc_name = db.get_pc_name(user_id)
    await UpdateClasses(user_id, pc_name, add=False).start(ctx)

@bot.command()
async def unregister(ctx:Ctx, secure:str=""):
    if secure=="seguro_que_quiero_borrar_mi_pj":
        db.unregister(ctx.author.id)
        await ctx.send("Tu PJ ha sido desregistrado!")
    else:
        await ctx.send("Manda este comando con el parametro 'seguro_que_quiero_borrar_mi_pj' para desregistrar a tu PJ.")



@bot.command()
async def hello(ctx:Ctx):
    await ctx.send("Hello!")

# with open("secrets", "r") as f:
#     token = f.read()

bot.run(os.environ.get("TOKEN"))
