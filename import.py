from bsky_utils import *
import sys


def find_or_create_channel(channel, did, service, session, guild_uri):
    # existing_channels = list_records(did, service, 'dev.dreary.discord.channel')
    # for echan in existing_channels:
    #     uri = traverse(echan, [{'value': {'id': channel['id']}}, 'uri'])
    #     if uri:
    #         print(f"Found existing channel record: {uri}")
    #         return uri
    if (existing_channel := get_record(did, 'dev.dreary.discord.channel', channel['id'], service, fatal=False)):
        print(f"Found existing channel record: {existing_channel['uri']}")
        return existing_channel['uri']
    print("No matching existing channel record found. Creating new channel record.")
    record = {
        'guild': guild_uri,
        # 'id': channel['id'],
        'name': channel['name'],
        'type': channel['type'],
        'categoryId': channel.get('categoryId'),
        'category': channel.get('category'),
        'topic': channel.get('topic')
    }
    return create_record(session, service, 'dev.dreary.discord.channel', record, rkey=channel['id'])

def find_or_create_guild(guild, did, service, session, base_dir):
    # existing_guilds = list_records(did, service, 'dev.dreary.discord.guild')
    # for eguild in existing_guilds:
    #     uri = traverse(eguild, [{'value': {'id': guild['id']}}, 'uri'])
    #     if uri:
    #         print(f"Found existing guild record: {uri}")
    #         return uri
    if (existing_guild := get_record(did, 'dev.dreary.discord.guild', guild['id'], service, fatal=False)):
        print(f"Found existing guild record: {existing_guild['uri']}")
        return existing_guild['uri']
    print("No matching existing guild record found. Creating new guild record.")

    if not (icon_path := guild.get('iconUrl')):
        raise Exception("Missing necessary guild field: iconUrl")

    blob, blob_type = upload_blob(session, service, str(base_dir / icon_path))
    if blob_type != "image":
        raise Exception(f"Unsupported blob type '{blob_type}'")
    record = {
        # 'id': guild['id'],
        'name': guild['name'],
        'icon': blob
    }
    return create_record(session, service, 'dev.dreary.discord.guild', record, rkey=guild['id'])

def find_or_create_author(author, eauth_index, did, service, session, base_dir):
    
    if author['id'] in eauth_index:
        return compose_uri(did, author['id'], collection='dev.dreary.discord.author')

    if not (avatar_path := author.get('avatarUrl')):
        raise Exception("Missing necessary guild field: avatarUrl")

    blob, blob_type = upload_blob(session, service, str(base_dir / avatar_path))
    if blob_type != "image":
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

def find_or_create_messages(messages, did, service, session, guild_uri, channel_uri, base_dir):
    existing_authors = list_records(did, service, 'dev.dreary.discord.author')
    eauth_index = {decompose_uri(uri)[2]: uri for eauth in existing_authors if (uri := eauth['uri'])}
    existing_messages = list_records(did, service, 'dev.dreary.discord.message')
    emsg_index = {decompose_uri(uri)[2]: uri for msg in existing_messages if (uri := msg['uri'])}
    for i, message in enumerate(messages):
        # at small scale it's more efficient to list_records rather than request each time
        # if get_record(did, 'dev.dreary.discord.message', message['id'], service, fatal=False):
        #     continue
        if message['id'] in emsg_index:
            print(f"Skipping existing message: {message['id']}")
            continue
        # message['author'] = find_or_create_author(message['author'], existing_authors, did, service, session, base_dir)
        # message['index'] = i # shrug, probably better than linked list but idk
        # message['timestamp'] = convert_timestamp_utc(message['timestamp'])
        # TODO: reaction emojis (particularly if svg files don't work), authors, custom emotes?
        # TODO: embeds, attachments, stickers, mentions
        # TODO: referece (with uri)
        # "reference": {
        #     "messageId": "1359202561080688762",
        #     "channelId": "1336910904679338079",
        #     "guildId": null
        # }
        author_uri = find_or_create_author(message['author'], eauth_index, did, service, session, base_dir)
        eauth_index[decompose_uri(author_uri)[2]] = author_uri
        record = {
            'type': message['type'],
            'timestamp': convert_timestamp_utc(message['timestamp']),
            'timestampEdited': message.get('timestampEdited'),
            'channelIndex': i,
            'callEndedTimestamp': message.get('callEndedTimestamp'),
            'isPinned': message.get('isPinned'),
            'content': message['content'],
            'author': author_uri,
            'guild': guild_uri, # redundant if we have channel uri?
            'channel': channel_uri
        }
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

    guild_uri = find_or_create_guild(data['guild'], did, service, session, base_dir)
    return
    channel_uri = find_or_create_channel(data['channel'], did, service, session, guild_uri)
    find_or_create_messages(data['messages'], did, service, session, guild_uri, channel_uri, base_dir)

    print('All done importing :3')


if __name__ == "__main__":
    main()

# https://github.com/Tyrrrz/DiscordChatExporter