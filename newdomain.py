from aiohttp import web 
from aiohttp.web import Request, Response, json_response
import random

routes = web.RouteTableDef()

# ====================================================== Global States ======================================================
# The items in my domain (items remain domain-level, but their placement per user is tracked by the hub)
DOMAIN_ITEMS = [
    # [Depth None] [Main-Lobby] [Self]
    {
        "name": "parchment",
        "description": "A piece of creased parchment with twisted bloody characters on it, it must be something important...",
        "verb": {
            "read": 'The parchment reads <q>Only Through Sacrifice Comes Reward</q>'
        }
    },
    # [Depth None] [Hallway] [Self]
    {
        "name": "torch",
        "description": "A torch with a tiny flame, the handle is long enough to carry it around. why not blow it to make it brighter...",
        "verb": {
            "use": 'Perfect! the torch becomes bright enough to lit up a wide expanse ahead. The crackling of the firewood eased your fear a little :)'
        }
    },
    # [Depth 0] [None] [Other]
    {
        "name": "dagger",
        "description": "A shiny silver dagger, staring at it for a long time evokes a strange desire to bring it closer to your wrist...",
        "verb": {
            "use": 'As if bewitched, you thrust it into your own arm! A searing pain strikes instantly, and blood drips from your fingertips to the altar, slowly filling up it. Suddenly the stone wall infront of you revealed an hidden entrance...'
        },
        "depth": 0
    },
    # [Depth 1] [None] [Other]
    {
        "name": "sword-of-gryffindor",
        "description": "A sword radiating a faint silver glow. The runes etched onto the blade seem to declare that nothing in the world can stand in its way.",
        "verb": {
            "use": 'You swing it forward, feeling an unprecedented surge of power! After a loud clang, The lock broke into two pieces! Countless ghosts scattering outside in panic in the sealed chamber, terrified of the holy sword in your hand...'
        },
        "depth": 1
    }
]


# /newhub globals
HUB_URL = None          # The url of the hub
DOMAIN_ID = None        # The assigned ID of the domain from the hub
DOMAIN_SECRET = None    # The assigned authentication of the domain from the hub
DOMAIN_LOCS = {         # The set of all locations and if they are visited
    "lobby": False,
    "hallway": False,
    "forbidden-library": False,
    "sealed-chamber": False,
    "inventory": True
}
DOMAIN_ITS = {
    "parchment": True,
    "dagger": False,
    "torch": False,
    "sword-of-gryffindor": False
}

NAME_2_ID = {}          # The helper dict for (item_name -> item_id)
ID_2_ITEM = {}          # The helper dict for (item_id -> item_info)

# Per-user state dictionary
# Key: user_id
# Value: dict with keys:
#   "arrived": bool (True if user is currently arrived)
#   "departed_time": float or int (timestamp or counter for the last departure)
#   "arrive_time": float or int (timestamp or counter for the last arrival)
#   "loc": str (the user's current location)
#   "lock_state": str ("locked", "open")
#   "altar_state": str ("locked", "open")
#   "parchment_state": str ("unmoved", "moved")
#   "torch_state": str ("without", "with")
#   "from": str (the direction or mode they arrived from)
USER_STATES = {}

# A simple counter to order arrivals/departures since no real time is provided.
# Every time a user arrives or departs, increment counters and store them.
ARRIVAL_COUNTER = 0
DEPARTURE_COUNTER = 0

# HELPER: Initialize the user
def new_user_state():
    # Return a fresh state for a new user
    return {
        "arrived": False,
        "arrive_time": 0,
        "depart_time": -1,  # No departure yet
        
        "loc": "lobby",
        "lock_state": "locked",
        "altar_state": "locked",
        "parchment_state": "unmoved",
        "torch_state": "dim",
        "from": None
    }

# HELPER: Synchronize the state of the user
def syn_user_state(user_id, user_state):
    USER_STATES[user_id]["arrived"] = user_state["arrived"]
    USER_STATES[user_id]["arrive_time"] = user_state["arrive_time"]
    USER_STATES[user_id]["depart_time"] = user_state["depart_time"]
    
    USER_STATES[user_id]["loc"] = user_state["loc"]
    USER_STATES[user_id]["lock_state"] = user_state["lock_state"]
    USER_STATES[user_id]["altar_state"] = user_state["altar_state"]
    USER_STATES[user_id]["parchment_state"] = user_state["parchment_state"]
    USER_STATES[user_id]["torch_state"] = user_state["torch_state"]
    USER_STATES[user_id]["from"] = user_state["from"]

# HELPER: Initialize the item location
async def register_item(app, user_id, item_name, location):
    target_id = NAME_2_ID.get(item_name, None)
    
    if target_id is not None:
        
        found_locations = []
        for loc in list(DOMAIN_LOCS.keys()):
            item_ids = await hub_query(app, user_id, location=loc)
            if target_id in item_ids:
                found_locations.append(loc)
                
        if not found_locations:
            await hub_transfer(app, user_id, target_id, location)

# HELPER: Update the location of an item
async def hub_transfer(app, user_id, item_id, to):
    async with app.client.post(HUB_URL+'/transfer', json={
        "domain": DOMAIN_ID,
        "secret": DOMAIN_SECRET,
        "user": user_id,
        "item": item_id,
        "to": to
    }) as resp:
        return await resp.json()

# HELPER: List the items in the given location / depth
async def hub_query(app, user_id, location=None, depth=None):
    data = {
        "domain": DOMAIN_ID,
        "secret": DOMAIN_SECRET,
        "user": user_id,
    }
    if location is not None:
        data["location"] = location
    else:
        data["depth"] = depth

    async with app.client.post(HUB_URL+'/query', json=data) as resp:
        return await resp.json()



# HELPER: Return the discription given the state of the parchment
def look_skeleton(parchment_state):
    if parchment_state == 'unmoved':
        return 'The skeleton is holding a parchment.'
    else:
        return 'The skeleton is holding nothing.'

# HELPER: Return the discription given the state of the altar
def look_altar(altar_state):
    if altar_state == "locked":
        return "You can see the mottled bloodstains on the altar, seeming to shimmer with a faint glow."
    else:
        return "The glow of the altar filled with fresh blood has dimmed significantly, as if it would take a long time to absorb the blood."

# HELPER: Return the discription given the state of the lock
def look_lock(lock_state):
    if lock_state == "locked":
        return "Though the lock is covered with a thick layer of rust, it remains incredibly hard, impervious to damage from ordinary weapons. Due to an ancient spell, it cannot be undone by simple incantations either."
    else:
        return "The lock is splited into half, the cut surface of the lock is still warm to the touch."

# HELPER: Return the congratulation if all rooms are unlocked & grant the user score 1.0
def congrats(state1, state2):
    if int(state1) + int(state2) == 2:
        return 1.0, "Congratulations! You have unravel all the mistries in this domain!"
    elif int(state1) + int(state2) == 1:
        return 0.5, "Keep it up! You are half way through this domain!"
    else:
        return 0.0, "You are just getting started! Keep exploring the domain!"
    


# HELPER: Return the location discription
def location_description(loc):
    if loc == "lobby":
        if DOMAIN_LOCS["lobby"]:
            return "You're back in the main lobby."
        else:
            return "You're in a dark lobby. By the faint firelight coming from the west, you can barely make out your surroundings. To the north, there is a giant door with a rusty lock engraved with runes, seemingly sealed by ancient magic. To the south, a skeleton lies on the ground, clutching something tightly in its hand. To the east are wooden doors through which you can feel frozen breeze."
    elif loc == "hallway":
        if DOMAIN_LOCS["hallway"]:
            return "You're in the hallway with an altar at the end of it."
        else:
            return "You're in a east-west direction hallway with a torch been hanging on the wall, intermittent whispering comes from the otherside of the hallway. At the end of the hallway, you find an altar staired with faded blood."
    elif loc == "forbidden-library":
        if DOMAIN_LOCS["forbidden-library"]:
            return "You're in the dark forbidden library with mountain of books"
        else:
            return "The wispering becomes larger and larger as you stepping down the stairs, you can see something is placed on a high pile of books at the end of the stairs."
    elif loc == "sealed-chamber":
        if DOMAIN_LOCS["sealed-chamber"]:
            return "You're in the sealed chamber with a large window"
        else:
            return "Gentle moonlight streamed through the floor-to-ceiling windows, casting its glow on something in front of it, while the rest of the room was completely empty, spider webs are everywhere."
    else:
        return ""
    
# HELPER: Return the discription for the item <- command [read item]
def item_description(item_id):
    return ID_2_ITEM[item_id].get("description", "")

# HELPER: Return the discription for the item's spesific verb <- command [read item]
def item_action(item_id, verb):
    v = ID_2_ITEM[item_id].get("verb", {})
    return v.get(verb, None)



# HELPER: Return the tiple of (found, item_id, current_location)
async def find_item_in_domain(app, user_id, name_or_id):
    # Initialization
    global DOMAIN_LOCS
    item_id = None
    
    # Get the asking item id
    try:
        item_id = int(name_or_id)
    except:
        item_id = NAME_2_ID.get(name_or_id, None)
        if not item_id:
            return False, None, None
        else:
            item_id = int(item_id)
    
    # Check every location
    for loc in DOMAIN_LOCS.keys():
        existing_ids = await hub_query(app, user_id, location=loc)
        if item_id in existing_ids:
            return True, item_id, loc

    # Not found
    return False, None, None

# HELPER: Return the list of items in a location
async def list_items_in_location(app, user_id, loc):
    items_here = []
    
    # (name, id) for items in the room
    item_ids = await hub_query(app, user_id, location=loc)
    for item_id in item_ids:
        item_name = ID_2_ITEM[item_id]["name"]
        items_here.append((item_name, item_id))

    return items_here



@routes.post('/newhub')
async def hub_handler(req: Request) -> Response:
    # Initialization
    global HUB_URL, DOMAIN_ID, DOMAIN_SECRET, DOMAIN_ITEMS
    text = await req.text()
    HUB_URL = text.strip()

    # Get register authentication from the hub (hub -> json)
    async with req.app.client.post(HUB_URL + '/register', json={
        'url': whoami,
        'name': "Final Project",
        'description': "An example domain based in a magic ruin.",
        'items': DOMAIN_ITEMS,
    }) as resp:
        data = await resp.json()
        if 'error' in data:
            return json_response(status=resp.status, data=data)
    
    DOMAIN_ID = data['id']
    DOMAIN_SECRET = data['secret']
    assigned_item_ids = data['items']
    
    # Store the domain items in global data structures
    for item_idx, item in enumerate(DOMAIN_ITEMS):
        item_id = assigned_item_ids[item_idx]
        item_verb = item.get("verb", {})
        item_info = {
            "name": item["name"],
            "description": item["description"],
            "verb": item_verb
        }
        item_depth = item.get("depth", None)
        if item_depth is not None:
            item_info["depth"] = item_depth

        # HELPER DATA
        ID_2_ITEM[item_id] = item_info
        NAME_2_ID[item["name"]] = item_id
    
    return json_response({"ok":"Domain registered."})

@routes.post('/arrive')
async def arrive_handler(req: Request) -> Response:
    # Initialization
    global ARRIVAL_COUNTER
    data = await req.json()
    app = req.app
    user_id = data['user']
    arrive_from = data.get('from','login')

    # Initialize domain states for a fresh start each arrive
    if user_id not in USER_STATES:
        USER_STATES[user_id] = new_user_state()
    user_state = USER_STATES[user_id]

    # Mark arrived
    user_state["arrived"] = True
    user_state["from"] = arrive_from
    ARRIVAL_COUNTER += 1
    user_state["arrive_time"] = ARRIVAL_COUNTER
    
    # Handle dropped items
    for item in data.get('dropped', []):
        item_id = item['id']
        if item_id not in ID_2_ITEM:
            info = {k:v for k,v in item.items() if k in ('name','description','verb','depth')}
            ID_2_ITEM[item_id] = info
            NAME_2_ID[info['name']] = item_id

        # Transfer the item to its original location (hub)
        pass

    # Handle prize items
    for item in data.get('prize',[]):
        item_id = item['id']
        if item_id not in ID_2_ITEM:
            info = {k:v for k,v in item.items() if k in ('name','description','verb','depth')}
            ID_2_ITEM[item_id] = info
            NAME_2_ID[info['name']] = item_id
        
        # Transfer the item to its original location (domain)
        item_depth = item.get('depth', 0)
        if item_depth == 0:
            await hub_transfer(app, user_id, item_id, "hallway")
        elif item_depth == 1:
            await hub_transfer(app, user_id, item_id, "forbidden-library")
        elif item_depth == 2:
            await hub_transfer(app, user_id, item_id, "sealed-chamber")

    # register the 2 no-depth item ('parchment', 'torch')
    await register_item(app, user_id, "parchment", "lobby")
    await register_item(app, user_id, "torch", "hallway")

    return web.Response(status=200)

@routes.post('/depart')
async def depart_handler(req: Request) -> Response:
    global DEPARTURE_COUNTER
    data = await req.json()
    user_id = data['user']
    # Mark user as departed
    if user_id not in USER_STATES:
        # If we never saw this user, just do nothing special
        USER_STATES[user_id] = new_user_state()
    user_state = USER_STATES[user_id]
    DEPARTURE_COUNTER += 1
    user_state["depart_time"] = DEPARTURE_COUNTER
    user_state["arrived"] = False

    return web.Response(status=200)

@routes.post('/dropped')
async def dropped_handler(req: Request) -> Response:
    data = await req.json()
    user_id = data['user']
    user_state = USER_STATES.get(user_id, new_user_state())
    return json_response(user_state["loc"])

@routes.post("/command")
async def command_handler(req : Request) -> Response:
    # Initialization
    data = await req.json()
    app = req.app
    user_id = data['user']
    user_state = USER_STATES.get(user_id, None)
    
    # user not arrived yet
    if not user_state:
        return web.Response(text="You have to journey to this domain before you can send it commands.")
    # If user departed more recently than arrived, return 409
    if user_state["depart_time"] > user_state["arrive_time"]:
        return web.Response(status=409, text="You have departed this domain. You must arrive again before issuing commands.")
    # user not arrived yet
    if not user_state["arrived"]:
        return web.Response(text="You have to journey to this domain before you can send it commands.")

    cmd = data['command']
    # Invalid command
    if not isinstance(cmd, list) or not all(isinstance(x,str) for x in cmd):
        return web.Response(text="I don't know how to do that.")
    # Void Command
    if len(cmd) == 0:
        return web.Response(text="I don't know how to do that.")

    # Split the command into [VERB ARGS]
    verb = cmd[0]
    args = cmd[1:]

    # For convenience
    USER_LOC = user_state["loc"]

    
    # ============================= Local Helper Functions ============================
    async def do_look():
        # Initialization
        nonlocal args, user_state, USER_LOC
        
        # command: [look]
        if len(args) == 0:
            # General discription for the room
            desc = location_description(USER_LOC)
           
            # Spesific naming for the items
            items_here = await list_items_in_location(app, user_id, USER_LOC)
            for (item_name, item_id) in items_here:
                desc += f"\nThere is a {item_name} <sub>{item_id}</sub> here."
            return web.Response(text=desc)
        
        # command: [look item]
        elif len(args) == 1:
            item_name = args[-1]
            found, item_id, where = await find_item_in_domain(app, user_id, item_name)
            
            # Named item not found
            if not found:
                return web.Response(text=f"There is no such thing called a {item_name} in this room.")
            # Sccessful case
            elif USER_LOC == where or "inventory" == where:
                return web.Response(text=item_description(item_id))
            # Other Invalid cases
            else:
                return web.Response(text="I don't know how to do that.")
        
        # command: <invalid>
        else:
            return web.Response(text="I don't know how to do that.")

    async def do_take():
        # Initialization
        nonlocal args, user_state, USER_LOC
        
        # command [take item]
        if len(args) == 1:
            name_or_id = args[-1]
            try:
                item_id = int(name_or_id)
                item_info = ID_2_ITEM.get(item_id, None)
                if not item_info:
                    return web.Response(text=f"There's no such thing here to take in this room")
                else:
                    item_name = str(item_info['name'])
            except:
                item_name = str(name_or_id)
            found, iid, where = await find_item_in_domain(app, user_id, item_name)
            
            # Named item not found
            if not found:
                return web.Response(text=f"There's no such thing here to take in this room")
            # Named item already taken
            elif where == 'inventory':
                return web.Response(text="You've already picked that, it's in your backpack!")
            # Successful case
            elif USER_LOC == where:
                res = await hub_transfer(app, user_id, iid, "inventory")
                if "error" in res:
                    return web.Response(text=f"There is something wrong when picking {item_name}")
                else:
                    if item_name == 'parchment':
                        user_state['parchment_state'] = 'moved'
                    return web.Response(text=f"You take the {item_name}.")
            else:
                return web.Response(text=f"There's no such thing here to take in this room")
                
        # command: <invalid>
        else:
            return web.Response(text="I don't know how to do that.")

    async def do_go():
        # Initialization
        nonlocal args, user_state, USER_LOC
        global DOMAIN_LOCS
        if len(args) == 0:
            return web.Response(text="Please spesify the direction.")
        direction = args[-1]

        # from lobby
        if USER_LOC == "lobby":
            # North -> sealed-chamber
            if direction == "north":
                if user_state['lock_state'] == 'open':
                    # change player location
                    USER_LOC = "sealed-chamber"
                    user_state["loc"] = USER_LOC
                    # return the discription
                    saved_args = args
                    args = []
                    resp = await do_look()
                    args = saved_args
                    # update the visited states
                    DOMAIN_LOCS["sealed-chamber"] = True
                    # Do the scoring
                    async with app.client.post(HUB_URL+'/score', json={
                        "domain": DOMAIN_ID,         
                        "secret": DOMAIN_SECRET, 
                        "user": user_id,   
                        "score": congrats(DOMAIN_LOCS["sealed-chamber"], DOMAIN_LOCS["forbidden-library"])[0]
                    }) as sc:
                        await sc.json()
                else:
                    resp = web.Response(
                        text="A massive stone gate stood imposingly, draped with numerous thick iron chains. These chains were tightly bound together by a colossal lock, as if sealing away the treasures (and ghosts) hidden behind it."
                    )
                return resp
            # South -> skeletons
            elif direction == "south":
                desc = "A creepy skeleton is sitting at the corner. " + look_skeleton(user_state['parchment_state'])
                return web.Response(text=desc)
            # West -> hallway
            elif direction == 'west':
                # change player location
                USER_LOC = "hallway"
                user_state["loc"] = USER_LOC
                # return the discription
                saved_args = args
                args = []
                resp = await do_look()
                args = saved_args
                # update the visited states
                DOMAIN_LOCS["hallway"] = True
                return resp
            # East -> quit
            elif direction == "east":
                return web.Response(text="$journey east")
            # Other directions
            else:
                return web.Response(text="Not a valid direction")
            
        # from hallway
        elif USER_LOC == "hallway":
            # East -> lobby
            if direction == "east":
                # change player location
                DOMAIN_LOCS['lobby'] = True
                USER_LOC = "lobby"
                user_state["loc"] = USER_LOC
                # return the discription
                saved_args = args
                args = []
                resp = await do_look()
                args = saved_args
                return resp
            
            # West -> forbidden-library
            elif direction == 'west' or direction == 'down':
                found, iid, where = await find_item_in_domain(app, user_id, 'torch')
                if user_state['altar_state'] == 'open' and where == 'inventory' and user_state['torch_state'] == 'light':
                    # change player location
                    USER_LOC = "forbidden-library"
                    user_state["loc"] = USER_LOC
                    # return the discription
                    saved_args = args
                    args = []
                    resp = await do_look()
                    args = saved_args
                    
                    DOMAIN_LOCS["forbidden-library"] = True
                    # Do the scoring
                    async with app.client.post(HUB_URL+'/score', json={
                        "domain": DOMAIN_ID,         
                        "secret": DOMAIN_SECRET, 
                        "user": user_id,   
                        "score": congrats(DOMAIN_LOCS["sealed-chamber"], DOMAIN_LOCS["forbidden-library"])[0]
                    }) as sc:
                        await sc.json()
                    return resp
                elif user_state['altar_state'] == 'locked':
                    return web.Response(text="Hmm... maybe there is some mechanism at the altar to open the way infront...")
                elif user_state['altar_state'] == 'open' and (where != 'inventory' or user_state['torch_state'] != 'light'):
                    return web.Response(text="It's too dark inside! You refuse to move forward...")
                else:
                    return web.Response(text="Hmm... maybe there is some mechanism at the altar to open the way infront...")
            
            # Other directions
            else:
                return web.Response(text="Just a old boring brick wall...")

        # from forbidden-library
        elif USER_LOC == "forbidden-library":
            # East -> hallway
            if direction == 'east' or direction == 'up':
                found, item_id, where = await find_item_in_domain(app, user_id, 'torch')
                if where != 'inventory':
                    return web.Response(text="In case falling down from the spirwal staris, I'd better pick up the torch...")
                else:
                    # change player location
                    USER_LOC = "hallway"
                    user_state["loc"] = USER_LOC
                    # return the discription
                    saved_args = args
                    args = []
                    resp = await do_look()
                    args = saved_args
                    return resp
            
            # Other directions
            else:
                return web.Response(text="You are blocked with mountians of books...")
        
        # from sealed-chamber
        elif USER_LOC == 'sealed-chamber':
            # South -> lobby
            if direction == 'south':
                # change player location
                USER_LOC = "lobby"
                user_state["loc"] = USER_LOC
                # return the discription
                saved_args = args
                args = []
                resp = await do_look()
                args = saved_args
                return resp
            
            # North -> window
            elif direction == 'north':
                return web.Response(text="You can see a blooded moon shedding scarlet light through the window, how beautiful it is...")
            
            # Other directions
            else:
                return web.Response(text="There is nothing here.")
                
        else:
            return web.Response(text="You can't go that way from here.")

    async def do_read():
        # Initialization
        nonlocal args, user_state, USER_LOC
        if len(args) == 0:
            return web.Response(text="Please spesify the item to read.")
        target = args[-1]
        
        # Check the location of the item to read
        found, iid, where = await find_item_in_domain(app, user_id, target)
        if not found:
            return web.Response(text="I don't know how to do that.")
        
        # Check if user location is valid
        vr = item_action(iid, "read")
        if vr is not None:
            if where == 'inventory' or where == USER_LOC:
                return web.Response(text=vr)
            else:
                return web.Response(text="I don't know how to do that.")
        return web.Response(text="I don't know how to do that.")

    async def do_use():
        # Initialization
        nonlocal args, user_state, USER_LOC
        global DOMAIN_ITS
        if len(args) == 0:
            return web.Response(text="Please specify what item to use and on which object to apply it.")
        item_name = args[0]
        
        # Use [dagger]
        if item_name == "dagger":
            found, item_id, where = await find_item_in_domain(app, user_id, item_name)
            if not found:
                return web.Response(text=f"I don't have {item_name}")
            else:
                if where != 'inventory' and where != USER_LOC:
                    return web.Response(text=f"I don't have {item_name} with me.")
                    
            # No objective to apply
            if len(args) < 2:
                return web.Response(text="I don't know how to do that.")
            
            # use [dagger] on [altar]
            if "altar" in args and USER_LOC == 'hallway':
                if DOMAIN_ITS['dagger']:
                    return web.Response(text="I do not want to scratch myself anymore...")
                
                DOMAIN_ITS['dagger'] = True
                user_state['altar_state'] = 'open'
                result = item_action(NAME_2_ID["dagger"], "use")
                return web.Response(text=result)
                    
            # use [dagger] on [altar]
            elif "altar" in args and USER_LOC != 'hallway':
                return web.Response(text="Maybe try somewhere else...")
            # use [dagger] ...
            else:
                return web.Response(text="I don't see the reason to do that...")
        
        # Use [sword-of-gryffindor]
        elif item_name == "sword-of-gryffindor":
            found, item_id, where = await find_item_in_domain(app, user_id, item_name)
            if not found:
                return web.Response(text=f"I don't have {item_name}")
            else:
                if where != 'inventory' and where != USER_LOC:
                    return web.Response(text=f"I don't have {item_name} with me.")
                
            # No objective to apply
            if len(args) < 2:
                return web.Response(text="I don't know how to do that.")
            
            # use [sword-of-gryffindor] on [lock]
            if "lock" in args and USER_LOC == 'lobby':
                if DOMAIN_ITS['sword-of-gryffindor']:
                    return web.Response(text="You feel that the magic within your body is insufficient to wield it once more...")
                
                DOMAIN_ITS['sword-of-gryffindor'] = True
                user_state['lock_state'] = 'open'
                result = item_action(NAME_2_ID["sword-of-gryffindor"], "use")
                    
                return web.Response(text=result)
            # use [sword-of-gryffindor] on [lock]  
            elif "lock" in args and USER_LOC != 'lobby':
                return web.Response(text="Maybe try somewhere else...")
            # use [sword-of-gryffindor] ...
            else:
                return web.Response(text="I don't see the reason to do that...")
        
        # Use [torch]
        elif item_name == "torch":
            found, item_id, where = await find_item_in_domain(app, user_id, item_name)
            
            # use [torch]
            if where == USER_LOC or where == 'inventory':
                if DOMAIN_ITS['torch']:
                    return web.Response(text="The torch is bright enough...")
                
                DOMAIN_ITS['torch'] = True
                user_state['torch_state'] = 'light'
                result = item_action(NAME_2_ID["torch"], "use")
                if result:
                    return web.Response(text=result)
                
            else:
                if where != 'inventory' and where != USER_LOC:
                    return web.Response(text=f"I don't have {item_name} with me.")
                
        # Use [parchment]
        elif item_name == "parchment":
            found, item_id, where = await find_item_in_domain(app, user_id, item_name)
            if not found:
                return web.Response(text=f"I don't have {item_name}")
            else:
                if where != 'inventory' and where != USER_LOC:
                    return web.Response(text=f"I don't have {item_name} with me.")
            
            return web.Response(text="I don't see though anyway I can USE it, may be just read it...")

        # Use other items
        else:
            return web.Response(text="Maybe try it somewhere else other than this domain...")

    
    
    # Handle special look verbs for skeleton/altar/lock
    if verb == "look" and len(args)==1:
        if args[0] == "skeleton":
            if USER_LOC == "lobby":
                return web.Response(text=look_skeleton(user_state['parchment_state']))
            else:
                return web.Response(text="I do not find any...")
            
        elif args[0] == "altar":
            if USER_LOC == "hallway":
                return web.Response(text=look_altar(user_state['altar_state']))
            else:
                return web.Response(text="I do not find any...")
            
        elif args[0] == "lock":
            if USER_LOC == "lobby":
                return web.Response(text=look_lock(user_state['lock_state']))
            else:
                return web.Response(text="I do not find any...")

    # Dispatch commands
    if verb == "look":
        resp = await do_look()
    elif verb == "read":
        resp = await do_read()
    elif verb == "take":
        resp = await do_take()
    elif verb == "go":
        resp = await do_go()
    elif verb == "use":
        resp = await do_use()
    else:
        resp = web.Response(text="I don't know how to do that.")

    # Synchronize the local changes of the user_state to the global user_state
    syn_user_state(user_id, user_state)
    return resp



def placeholder_for_strings():
    pass

@web.middleware
async def allow_cors(req, handler):
    resp = await handler(req)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

async def start_session(app):
    from aiohttp import ClientSession, ClientTimeout
    app.client = ClientSession(timeout=ClientTimeout(total=3))

async def end_session(app):
    await app.client.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default="0.0.0.0")
    parser.add_argument('-p','--port', type=int, default=3400)
    args = parser.parse_args()

    import socket
    whoami = socket.getfqdn()
    if '.' not in whoami: whoami = 'localhost'
    whoami += ':'+str(args.port)
    whoami = 'http://' + whoami
    print("URL to type into web prompt:\n\t"+whoami)
    print()

    from aiohttp.web import Application
    app = Application(middlewares=[allow_cors])
    app.on_startup.append(start_session)
    app.on_shutdown.append(end_session)
    app.add_routes(routes)
    web.run_app(app, host=args.host, port=args.port)
