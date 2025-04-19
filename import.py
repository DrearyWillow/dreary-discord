from bsky_utils import *
import sys
import shutil

def safe_delete_tmp_dir(tmp_dir, base_dir):
    try:
        tmp_dir = tmp_dir.resolve()
        base_dir = base_dir.resolve()
        if base_dir in tmp_dir.parents and tmp_dir.is_dir():
            shutil.rmtree(tmp_dir)
            print(f"Deleted: {tmp_dir}")
        else:
            raise ValueError("Refusing to delete: tmp_dir is not inside the expected base directory.")
    except Exception as e:
        print(f"Error deleting {tmp_dir}: {e}")

def retrieve_json_str(url, base_dir):
    if not url.startswith('https://'):
        with open(base_dir / url, "r", encoding="utf-8") as f:
            return f.read()
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def retrieve_blob_path(url, base_dir, tmp_dir):
    if not url.startswith('https://'):
        return str(base_dir / url)

    filepath = tmp_dir / url.split("/")[-1].split("?")[0]

    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return filepath
    

def find_or_create_channel(channel, did, service, session, guild_uri):
    if (existing_channel := get_record(did, 'dev.dreary.discord.channel', channel['id'], service, fatal=False)):
        print(f"Found existing channel record: {existing_channel['uri']}")
        return existing_channel['uri']
    print("No matching existing channel record found. Creating new channel record.")
    record = {
        'guild': guild_uri,
        'name': channel['name'],
        'type': channel['type'],
        'categoryId': channel.get('categoryId'),
        'category': channel.get('category'),
        'topic': channel.get('topic')
    }
    return create_record(session, service, 'dev.dreary.discord.channel', record, rkey=channel['id'])


def find_or_create_guild(guild, did, service, session, base_dir, tmp_dir):
    if (existing_guild := get_record(did, 'dev.dreary.discord.guild', guild['id'], service, fatal=False)):
        print(f"Found existing guild record: {existing_guild['uri']}")
        return existing_guild['uri']
    print("No matching existing guild record found. Creating new guild record.")

    if not (icon_path := guild.get('iconUrl')):
        raise Exception("Missing necessary guild field: iconUrl")

    blob_location = retrieve_blob_path(icon_path, base_dir, tmp_dir)
    blob = upload_blob(session, service, blob_location)
    if blob["mimeType"].split('/')[0] != "image":
        raise Exception(f"Unsupported blob type '{blob_type}'")
    record = {
        'name': guild['name'],
        'icon': blob
    }
    return create_record(session, service, 'dev.dreary.discord.guild', record, rkey=guild['id'])


def find_or_create_author(author, eauth_index, did, service, session, base_dir, tmp_dir):
    if author['id'] in eauth_index:
        return compose_uri(did, author['id'], collection='dev.dreary.discord.author')

    if not (avatar_path := author.get('avatarUrl')):
        raise Exception("Missing necessary author field: avatarUrl")

    blob_location = retrieve_blob_path(avatar_path, base_dir, tmp_dir)
    blob = upload_blob(session, service, blob_location)
    if blob["mimeType"].split('/')[0] != "image":
        raise Exception(f"Unsupported blob type '{blob_type}'")
    
    record = {
        'name': author['name'],
        'discriminator': author.get('discriminator'),
        'nickname': author.get('nickname'),
        'color': author.get('color'),
        'isBot': author.get('isBot'),
        'roles': author.get('roles'),
        'avatar': blob
    }
    return create_record(session, service, 'dev.dreary.discord.author', record, rkey=author['id'])

def find_or_create_sticker(sticker, esticker_index, did, service, session, base_dir, tmp_dir):
    if sticker['id'] in esticker_index:
        return compose_uri(did, sticker['id'], collection='dev.dreary.discord.sticker')

    if not (sticker_path := sticker.get('sourceUrl')):
        raise Exception("Missing necessary sticker field: sourceUrl")

    record = {
        'name': sticker['name'],
        'format': sticker['format'],
        'source': retrieve_json_str(sticker_path, base_dir)
    }
    return create_record(session, service, 'dev.dreary.discord.sticker', record, rkey=sticker['id'])


def populate_indexes(did, service):
    indexes = {}
    for rtype in ['author', 'message', 'sticker', 'embed', 'attachment']: # 'channel', 'guild'
        existing_records = list_records(did, service, f'dev.dreary.discord.{rtype}')
        indexes[rtype] = {decompose_uri(uri)[2]: uri for record in existing_records if (uri := record['uri'])}
        print(f'{rtype} index loaded')
    return indexes

def find_or_create_messages(messages, indexes, did, service, session, guild_uri, channel_uri, base_dir, tmp_dir):
    # existing_authors = list_records(did, service, 'dev.dreary.discord.author')
    # eauth_index = {decompose_uri(uri)[2]: uri for eauth in existing_authors if (uri := eauth['uri'])}
    # print("Author index loaded")
    # existing_messages = list_records(did, service, 'dev.dreary.discord.message')
    # emsg_index = {decompose_uri(uri)[2]: uri for msg in existing_messages if (uri := msg['uri'])}
    # print("Message index loaded")
    # TODO: switch to applywrites
    # for i, message in enumerate(messages):
    for message in messages:
        # at small scale it's more efficient to list_records rather than request each time
        # if get_record(did, 'dev.dreary.discord.message', message['id'], service, fatal=False):
        #     continue
        if message['id'] in indexes['message']:
            print(f"Skipping existing message: {message['id']}")
            continue
        # TODO: reaction emojis (particularly if svg files don't work), authors, custom emotes?
        # TODO: embeds, attachments, stickers
        # TODO: some things shouldn't be lexicons? like reactions, probably stickers, attachments, embeds too? it doesn't really matter if they have an id, i can include it anyways 
        author_uri = find_or_create_author(message['author'], indexes['author'], did, service, session, base_dir, tmp_dir)
        indexes['author'][decompose_uri(author_uri)[2]] = author_uri
        # alternatively i could replace just the values i want in the original message, 
        # which has the advantage of automatically accomodating unexpected fields
        # this also has the disadvantage of automatically accomodating unexpected fields
        record = {
            'type': message['type'],
            'timestamp': convert_timestamp_utc(message['timestamp']),
            'timestampEdited': message.get('timestampEdited'),
            # 'channelIndex': i, # timestamp is probably cannonical
            'callEndedTimestamp': message.get('callEndedTimestamp'),
            'isPinned': message.get('isPinned'),
            'content': message['content'],
            'author': author_uri,
            'guild': guild_uri,
            'channel': channel_uri
        }

        if ref := message.get('reference'):
            record['reference'] = {}
            record['reference']['message'] = compose_uri(did, ref.get('messageId'), collection='dev.dreary.discord.message')
            record['reference']['channel'] = compose_uri(did, ref.get('channelId'), collection='dev.dreary.discord.channel')
            record['reference']['guild'] = compose_uri(did, ref.get('guildId') or "0", collection='dev.dreary.discord.guild')
        
        field_configs = [
            ('mentions', 'author', find_or_create_author),
            ('stickers', 'sticker', find_or_create_sticker),
            ('embeds', 'embed', find_or_create_embed),
            ('reactions', 'reaction', find_or_create_reaction),
        ]

        for msg_field, index_key, creator_func in field_configs:
            if not (items := message.get(msg_field)):
                continue
            record[msg_field] = []
            for item in items:
                uri = creator_func(item, indexes[index_key], did, service, session, base_dir, tmp_dir)
                record[msg_field].append(uri)
                indexes[index_key][decompose_uri(uri)[2]] = uri

        # for mention in message.get('mentions'):
        #     record['mentions'] = []
        #     author_uri = find_or_create_author(mention, indexes['author'], did, service, session, base_dir, tmp_dir)
        #     record['mentions'].append(author_uri)
        #     indexes['author'][decompose_uri(author_uri)[2]] = author_uri
        # for sticker in message.get('stickers'):
        #     record['stickers'] = []
        #     sticker_uri = find_or_create_sticker(sticker, embed_index, did, service, session, base_dir, tmp_dir)
        #     record['stickers'].append(sticker_uri)
        #     indexes['sticker'][decompose_uri(sticker_uri)[2]] = sticker_uri
        # for embed in message.get('embeds'):
        #     record['embeds'] = []
        #     embed_uri = find_or_create_embed(embed, embed_index, did, service, session, base_dir, tmp_dir)
        #     record['embeds'].append(embed_uri)
        #     indexes['embed'][decompose_uri(embed_uri)[2]] = embed_uri
        # for reaction in message.get('reactions'):
        #     record['reactions'] = []
        #     reaction_uri = find_or_create_reaction(reaction, embed_index, did, service, session, base_dir, tmp_dir)
        #     record['reactions'].append(reaction_uri)
        #     indexes['reaction'][decompose_uri(reaction_uri)[2]] = reaction_uri

        create_record(session, service, 'dev.dreary.discord.message', record, rkey=message['id'])

def main():
    with open('config.json') as f:
        config = json.load(f)
    HANDLE = config.get('HANDLE')
    PASSWORD = config.get('PASSWORD')
    if not (HANDLE and PASSWORD):
        print('Enter credentials in config.json')
        return
    
    did = resolve_handle(HANDLE)
    service = get_service_endpoint(did)
    session = get_session(did, PASSWORD, service)

    if len(sys.argv) < 2:
        input_file = input('Input an input file: ')
        if input_file == '': return
    else:
        input_file = sys.argv[1]

    input_file = Path(input_file)
    base_dir = input_file.parent

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        raise Exception("Input a valid JSON file path")

    tmp_dir = base_dir / f'tmp-{generate_timestamp()}'
    tmp_dir.mkdir(parents=True, exist_ok=True)

    guild_uri = find_or_create_guild(data['guild'], did, service, session, base_dir, tmp_dir)
    channel_uri = find_or_create_channel(data['channel'], did, service, session, guild_uri)
    indexes = populate_indexes(did, service)
    find_or_create_messages(data['messages'], indexes, did, service, session, guild_uri, channel_uri, base_dir, tmp_dir)

    print('All done importing :3')
    safe_delete_tmp_dir(tmp_dir, base_dir)


if __name__ == "__main__":
    main()

# https://github.com/Tyrrrz/DiscordChatExporter