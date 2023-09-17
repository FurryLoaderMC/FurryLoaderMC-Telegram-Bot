import copy
import json
import os
import re
import threading
import time
import traceback
from datetime import datetime
from enum import Enum

import minestat
import socketio
import telebot
from loguru import logger
from telebot import apihelper


# 判断文件夹是否存在，不存在则创建
def create_file_if(file_name):
    if not os.path.exists(file_name):
        with open(file_name, 'w') as f:
            f.write('{}')


if not os.path.exists('data'):
    os.makedirs('data')

create_file_if('data/id.json')
# create_file_if('data/latest_player.json')
create_file_if('data/username_id.json')

logger.add("logs/app_{time}.log", rotation="00:00", retention="10 days",
           format="[{level}] {time:MM-DD HH:mm:ss.SSS} ({module}:{line}) - {message}")


# 读取对应的json并且解析
def read_data(file_type, folder='data'):
    if folder == '':
        with open(f'{file_type}.json', encoding='utf8') as f:
            data = json.load(f)
    else:
        with open(f'{folder}/{file_type}.json', encoding='utf8') as f:
            data = json.load(f)
    return data


# 将对应的json写入
def write_data(file_type, data):
    with open(f'data/{file_type}.json', 'w') as f:
        f.write(json.dumps(data))


# 处理tg特殊字符
def tg_escape(text):
    return text.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')


# 判断配置文件是否存在，若不存在则报错并停止运行
if not os.path.exists('config.json'):
    logger.error('config.json 不存在，请先创建 config.json')
    exit(1)

# 读取配置
config = read_data('config', '')

# 变量
apihelper.proxy = {'http': config['proxy']}
bot = telebot.TeleBot(config['bot_token'], parse_mode='MARKDOWN')
group_id = config['group_id']

help_text = f'''
{config['bot_name']} 帮助菜单  
`/status` - 获取服务器状态  
`/performance` - 获取服务器性能信息
`/list` - 获取服务器上的玩家列表  
`/bind` - 绑定你的 MC 用户名  
`/unbind` - 解绑你的 MC 用户名  
`/get_me` - 获取你的信息
`/at` - 在服务器里 @ 一个人
'''

bot.set_my_commands([
    telebot.types.BotCommand('/status', '服务器状态'),
    telebot.types.BotCommand('/performance', '服务器性能信息'),
    telebot.types.BotCommand('/list', '玩家列表'),
    telebot.types.BotCommand('/bind', '绑定 MC 用户名（手动输入 /bind 用户名）'),
    telebot.types.BotCommand('/unbind', '解绑 MC 用户名'),
    telebot.types.BotCommand('/get_me', '获取用户信息'),
    telebot.types.BotCommand('/at', '在服务器里 @ 一个人（手动输入 /at 用户名）'),
])


# Handle '/start' and '/help'
@bot.message_handler(commands=['help', 'start'])
def send_welcome(message_local):
    logger.info({'help', str(message_local.from_user.username)})
    bot.reply_to(message_local, help_text)


def empty_callback(*args):
    pass


@bot.message_handler(commands=['list'])
def send_player_list(message_local):
    logger.info({'list', str(message_local.from_user.username)})

    sio.emit('players', namespace='/status', callback=empty_callback)


@bot.message_handler(commands=['status'])
def send_server_status(message_local):
    logger.info({'status', str(message_local.from_user.username)})
    ms = get_server_status()
    status = f'{config["server_name"]} 服务器状态\n'
    status += f'服务器地址：`{config["server_ip_export"]}`\n'
    if ms.online:
        status += '服务器版本：' + ms.version + '\n'
        status += '在线玩家数：' + str(ms.current_players) + '/' + str(ms.max_players) + '\n'
        status += '服务器描述：' + ms.stripped_motd
        bot.reply_to(message_local, status)
    else:
        bot.reply_to(message_local, status + '服务器离线')


# @bot.message_handler(commands=['getID'])
# def send_welcome(message):
#     bot.reply_to(message, message.chat.id)


@bot.message_handler(commands=['performance'])
def send_performance(message_local):
    logger.info({'performance', str(message_local.from_user.username)})

    sio.emit('performance', namespace='/status', callback=empty_callback)


@bot.message_handler(commands=['bind'])
def bind_mc(message_local):
    logger.info({'bind', str(message_local.from_user.username)})
    if message_local.text[6:] != '':
        # 判断是否有@机器人用户名
        if message_local.text.find(config['bot_username']) != -1:
            # 发送消息
            bot.reply_to(message_local, '请手动输入 `/bind 用户名`')
            return

        pattern = re.compile(r'^\w+$')
        if not pattern.match(message_local.text[6:]):
            bot.reply_to(message_local, 'MC 用户名只能包含英文、数字和下划线')
            return
        id_data = read_data('id')
        # 判断有没有人绑定过这个mc用户名
        player_id = get_id_by_mc_username(message_local.text[6:])
        if player_id:
            bot.reply_to(message_local,
                         f'这个 MC 用户名已经被 {get_tg_username_by_id(player_id)} 绑定过了')
            return

        id_data[str(message_local.from_user.id)] = message_local.text[6:]
        write_data('id', id_data)
        bot.reply_to(message_local, f'绑定成功：`{message_local.text[6:]}`')
    else:
        bot.reply_to(message_local, '请在 `/bind` 命令后面加上你的 MC 用户名')

    # 判断tg用户名是否为空
    if message_local.from_user.username:
        username_id_data = read_data('username_id')
        username_id_data[str(message_local.from_user.id)] = message_local.from_user.username
        write_data('username_id', username_id_data)


@bot.message_handler(commands=['unbind'])
def unbind_mc(message_local):
    logger.info({'unbind', str(message_local.from_user.username)})
    id_data = read_data('id')
    if str(message_local.from_user.id) in id_data:
        del id_data[str(message_local.from_user.id)]
        write_data('id', id_data)
        bot.reply_to(message_local, '解绑成功')
    else:
        bot.reply_to(message_local, '你还没有绑定 MC 用户名')


@bot.message_handler(commands=['get_me'])
def get_me(message_local):
    logger.info({'get_me', str(message_local.from_user.username)})
    userinfo = bot.get_chat(message_local.from_user.id)
    reply_str = f'''
你的用户名：`{userinfo.username}`
你的 ID：`{userinfo.id}`
'''
    if read_data('id').get(str(message_local.from_user.id)):
        reply_str += f'你绑定的 MC 用户名：`{read_data("id").get(str(message_local.from_user.id))}`'
    else:
        reply_str += '你还没有绑定 MC 用户名'
    bot.reply_to(message_local, reply_str)

    if message_local.from_user.username:
        username_id_data = read_data('username_id')
        username_id_data[str(message_local.from_user.id)] = message_local.from_user.username
        write_data('username_id', username_id_data)


# 分割@与消息
def parse_message(text, entities):
    if not entities:
        return [{
            'type': 'text',
            'id': None,
            'content': text
        }]
    else:
        message_local = []
        # 遍历entities
        for entity in entities:
            # 判断是不是第一个entity
            if entity == entities[0]:
                # 判断entity前面的字符串是否为空
                if text[:entity.offset] != '':
                    # 如果是第一个entity就去掉后面的空格并且添加到message
                    message_local.append({
                        'type': 'text',
                        'id': None,
                        'content': text[:entity.offset].strip()
                    })

            # 判断是否为mention
            if entity.type == 'mention':
                # 截取@后面的用户名
                user_name = text[entity.offset + 1:entity.offset + entity.length]
                message_local.append({'type': 'at',
                                      'id': get_id_by_tg_username(user_name),
                                      'content': user_name,
                                      })
            elif entity.type == 'text_mention':
                message_local.append({'type': 'at',
                                      'id': entity.user.id,
                                      'content': get_tg_username_by_id_noformat(entity.user.id)})
            else:
                # 否则就是普通文本
                message_local.append({
                    'type': 'text',
                    'id': None,
                    'content': text[entity.offset:entity.offset + entity.length]
                })

            # 判断如果不是最后一个entity
            if entity != entities[-1]:
                # 判断和下一个entity之间的字符串是否为空
                if text[entity.offset + entity.length:entities[entities.index(entity) + 1].offset] != '':
                    # 如果不为空就去掉首尾空格并且添加到message
                    message_local.append({
                        'type': 'text',
                        'id': None,
                        'content': text[entity.offset + entity.length:entities[
                            entities.index(entity) + 1].offset].strip()
                    })
            else:
                # 判断后面的字符串是否为空
                if text[entity.offset + entity.length:] != '':
                    # 如果是最后一个entity就去掉前面的空格并且添加到message
                    message_local.append({
                        'type': 'text',
                        'id': None,
                        'content': text[entity.offset + entity.length:].strip()
                    })

        return message_local


# 在tg里@mc用户名并且发送到ws
@bot.message_handler(commands=['at'])
def at_mc(message_local):
    logger.info({'at', str(message_local.from_user.username)})
    if message_local.text[4:] != '':
        # 判断是否有@机器人用户名
        if message_local.text.find(config['bot_username']) != -1:
            # 发送消息
            bot.reply_to(message_local, '请手动输入 `/at 用户名`')
            return

        id_data = read_data('id')
        # 判断用户是否绑定
        if str(message_local.from_user.id) in id_data:
            player_id = get_id_by_mc_username(id_data[str(message_local.from_user.id)])

            # 复制message模板
            message_to_send = copy.deepcopy(message_template)

            if player_id:
                message_to_send['sender']['minecraft_name'] = get_mc_username_by_id(player_id)
                message_to_send['sender']['telegram_name'] = get_tg_username_by_id_noformat(player_id)
                message_to_send['sender']['telegram_id'] = player_id
                message_to_send['message']['id'] = message_local.message_id
                message_to_send['message']['content'].append({
                    'type': 'at',
                    'id': None,
                    # @的用户名（从第5个字符到空格处（如果没有空格就是到最后））
                    'content': message_local.text[4:].split(' ')[0],
                })
                # 判断是否有第二个空格
                if len(message_local.text[4:].split(' ')) > 1:
                    message_to_send['message']['content'].append({
                        'type': 'text',
                        'id': None,
                        # @后面的消息（从第2个空格到最后（如果没有第二个空格就返回None））
                        'content': ' '.join(message_local.text[4:].split(' ')[1:]),
                    })
                sio.emit('chat', message_to_send, namespace='/message')
                result_message = bot.reply_to(message_local, f'已发送')
                # 五秒后删除消息
                time.sleep(5)
                bot.delete_message(message_local.chat.id, result_message.message_id)

        else:
            bot.reply_to(message_local, '你需要先绑定 MC 用户名')
    else:
        bot.reply_to(message_local, '请在 `/at` 命令后面加上你要 @ 的 MC 用户名')


@bot.message_handler(func=lambda message: True,
                     content_types=['text', 'photo', 'video', 'audio', 'voice', 'sticker', 'document'])
def if_all(message_local):
    try:
        # logger.info(message)
        logger.info(
            {'telegram 收到消息', message_local.content_type, message_local.text, message_local.from_user.username})

        # 复制message模板
        message_to_send = copy.deepcopy(message_template)

        message_to_send['sender']['minecraft_name'] = get_mc_username_by_id(message_local.from_user.id)
        message_to_send['sender']['telegram_name'] = get_tg_username_by_id_noformat(message_local.from_user.id)
        message_to_send['sender']['telegram_id'] = message_local.from_user.id
        message_to_send['message']['id'] = message_local.message_id

        if message_local.reply_to_message:
            reply_str = ''
            content_type_zh = {
                'photo': '图片',
                'video': '视频',
                'audio': '音频',
                'voice': '语音',
                'sticker': '贴纸',
                'document': '文件',
            }

            if message_local.reply_to_message.content_type == 'text':
                reply_str = message_local.reply_to_message.text
            # 判断是否在列表中
            elif message_local.reply_to_message.content_type in content_type_zh.keys():
                reply_str = '[' + content_type_zh[message_local.reply_to_message.content_type] + ']'

                if message_local.reply_to_message.content_type == 'photo':
                    file = bot.get_file(message_local.photo[-1].file_id)
                    reply_str += ' (' + file.file_path + ')'
                elif message_local.reply_to_message.content_type == 'video':
                    reply_str += ' (' + message_local.reply_to_message.video.file_name + ')'
                elif message_local.reply_to_message.content_type == 'audio':
                    reply_str += ' (' + message_local.reply_to_message.audio.file_name + ')'
                elif message_local.reply_to_message.content_type == 'document':
                    reply_str += ' (' + message_local.reply_to_message.document.file_name + ')'
                elif message_local.reply_to_message.content_type == 'sticker':
                    reply_str += ' ' + message_local.reply_to_message.sticker.emoji

                if message_local.reply_to_message.caption:
                    reply_str += ' ' + message_local.reply_to_message.caption

            if reply_str != '':
                message_to_send['message']['content'].append({
                    'type': 'reply',
                    'id': message_local.reply_to_message.message_id,
                    'content': reply_str,
                })

        if message_local.content_type == 'text':
            if message_local.text.find('好烧') != -1 or message_local.text.find('烧起来') != -1 \
                    or message_local.text.find('🥵') != -1:
                bot.send_message(message_local.chat.id, '🥵🥵🥵')

            # if read_data('id').get(str(message.from_user.id)):
            # 给message_to_send['content']['message']添加{'type': 'text', 'content': 'xxx'}
            message_to_send['message']['content'].extend(parse_message(message_local.text,
                                                                       message_local.entities))
            sio.emit('chat', message_to_send, namespace='/message')

        else:
            # if read_data('id').get(str(message.from_user.id)):
            if message_local.content_type == 'photo':
                file = bot.get_file(message_local.photo[-1].file_id)
                message_to_send['message']['content'].append({
                    'type': 'photo',
                    'id': None,
                    'content': file.file_path,
                })
            elif message_local.content_type == 'video':
                message_to_send['message']['content'].append({
                    'type': 'video',
                    'id': None,
                    # 文件名
                    'content': message_local.video.file_name,
                })
            elif message_local.content_type == 'audio':
                message_to_send['message']['content'].append({
                    'type': 'audio',
                    'id': None,
                    # 文件名
                    'content': message_local.audio.file_name,
                })
            elif message_local.content_type == 'voice':
                message_to_send['message']['content'].append({
                    'type': 'voice',
                    'id': None,
                    'content': None
                })
            elif message_local.content_type == 'sticker':
                message_to_send['message']['content'].append({
                    'type': 'sticker',
                    'id': None,
                    'content': message_local.sticker.emoji,
                })
            elif message_local.content_type == 'document':
                message_to_send['message']['content'].append({
                    'type': 'document',
                    'id': None,
                    # 文件名
                    'content': message_local.document.file_name,
                })

            if message_local.caption:
                # print(message.caption)
                message_to_send['message']['content'].extend(parse_message(message_local.caption,
                                                                           message_local.caption_entities))
            sio.emit('chat', message_to_send, namespace='/message')

        if message_local.from_user.username:
            username_id_data = read_data('username_id')
            username_id_data[str(message_local.from_user.id)] = message_local.from_user.username
            write_data('username_id', username_id_data)
    except Exception as e:
        traceback_info = traceback.format_exc()
        logger.error(e)
        logger.error(traceback_info)


def send_message(content, disable_web_page_preview=True):
    logger.info({'tg 发送消息', content})
    bot.send_message(group_id, content, disable_web_page_preview=disable_web_page_preview)


def tg_polling():
    logger.info('telegram 启动轮询')
    try:
        bot.infinity_polling(logger_level=None)
    except Exception as e:
        traceback_info = traceback.format_exc()
        logger.error(e)
        logger.error(traceback_info)


tr_tg_polling = threading.Thread(target=tg_polling)
tr_tg_polling.start()


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, Enum):
            return o.value
        return json.JSONEncoder.default(self, o)


def compare_arrays(array1, array2):
    set1 = set(array1)
    set2 = set(array2)
    added_local = set2 - set1  # 新增的元素
    removed_local = set1 - set2  # 删除的元素
    return list(added_local), list(removed_local)


def get_server_status():
    return minestat.MineStat(config['server_ip'], config['server_port'])


def get_player_list(ms_local):
    if ms_local.online:
        return ms_local.player_list


# 通过mc用户名判断是否绑定，如果绑定则返回对应的id
def get_id_by_mc_username(mc_username):
    data_id = read_data('id')
    if mc_username in data_id.values():
        return [k for k, v in data_id.items() if v == mc_username][0]
    else:
        return None


# 通过id获取mc用户名
def get_mc_username_by_id(user_id):
    data_id = read_data('id')
    if str(user_id) in data_id.keys():
        return data_id[str(user_id)]
    else:
        return None


def get_tg_username_by_id(user_id):
    if not user_id:
        return None
    try:
        userinfo = bot.get_chat(user_id)
        # 判断是否有tg昵称
        if userinfo.username:
            # 判断是否有last_name
            if userinfo.last_name:
                ret_str = f'[{userinfo.first_name} {userinfo.last_name}](t.me/{userinfo.username})'
            else:
                ret_str = f'[{userinfo.first_name}](t.me/{userinfo.username})'
        else:
            if userinfo.last_name:
                ret_str = f'{userinfo.first_name} {userinfo.last_name}'
            else:
                ret_str = f'{userinfo.first_name}'
        if ret_str:
            return ret_str
        else:
            return None
    except Exception as e:
        traceback_info = traceback.format_exc()
        logger.error(e)
        logger.error(traceback_info)
        return None


def get_tg_username_by_id_noformat(user_id):
    if not user_id:
        return None
    userinfo = bot.get_chat(user_id)
    if userinfo.last_name:
        ret_str = f'{userinfo.first_name} {userinfo.last_name}'
    else:
        ret_str = f'{userinfo.first_name}'
    if ret_str:
        return ret_str
    else:
        return None


def get_id_by_tg_username(tg_username):
    data_id = read_data('username_id')
    if tg_username in data_id.values():
        return [k for k, v in data_id.items() if v == tg_username][0]
    else:
        return None


# 判断字符串是否为空，如果为空则直接设置这个字符串为另一个字符串，如果不为空则在后面加上分隔符再加另一个字符串
def set_str_if_empty(str1, str2, separator):
    if str1 == '':
        return str2
    else:
        return str1 + separator + str2


# message 模板
message_template = {
    "sender": {
        "minecraft_name": "",
        'minecraft_uuid': "",
        "telegram_name": "",
        "telegram_id": 0
    },
    "message": {
        "id": 0,
        "content": [
        ]
    }
}

sio = socketio.Client()


@sio.event(namespace='/status')
def message(data):
    logger.info({'status 收到消息', data})


@sio.event(namespace='/message')
def message(data):
    logger.info({'message 收到消息', data})


@sio.on('join', namespace='/message')
def on_message(data):
    logger.info({'收到 join 事件', data})
    data_json = json.loads(data)
    player_name = data_json['sender']['minecraft_name']
    player_id = get_id_by_mc_username(player_name)
    if player_id:
        if get_tg_username_by_id(player_id):
            send_message(f'`{player_name}` ({get_tg_username_by_id(player_id)}) 加入了服务器')
        else:
            send_message(f'`{player_name}` 加入了服务器')
    else:
        send_message(f'`{player_name}` 加入了服务器')


@sio.on('quit', namespace='/message')
def on_message(data):
    logger.info({'收到 quit 事件', data})
    data_json = json.loads(data)
    player_name = data_json['sender']['minecraft_name']
    player_id = get_id_by_mc_username(player_name)
    if player_id:
        if get_tg_username_by_id(player_id):
            send_message(f'`{player_name}` ({get_tg_username_by_id(player_id)}) 离开了服务器')
        else:
            send_message(f'`{player_name}` 离开了服务器')
    else:
        send_message(f'`{player_name}` 离开了服务器')


@sio.on('death', namespace='/message')
def on_message(data):
    logger.info({'收到 death 事件', data})
    data_json = json.loads(data)
    player_name = data_json['sender']['minecraft_name']
    player_id = get_id_by_mc_username(player_name)

    death_dict = data_json["message"]["content"]
    death_format = death_dict[0]['content']
    death_person = death_dict[1]['content']
    death_cause_person = None
    death_cause = None
    # 判断有没有第三个参数
    if len(death_dict) > 2:
        death_cause_person = death_dict[2]['content']
    # 判断有没有第四个参数
    if len(death_dict) > 3:
        death_cause = death_dict[3]['content']

    # 读取res/zh_cn.json
    zh_cn_data = read_data('zh_cn', 'res')
    death_format_value = zh_cn_data[death_format]

    death_str = death_format_value
    if player_id:
        death_str = death_str.replace('%1$s', f'`{death_person}` ({get_tg_username_by_id(player_id)}) ')
    else:
        death_str = death_str.replace('%1$s', f'`{death_person}` ')

    if death_cause_person:
        if death_cause_person in zh_cn_data.keys():
            death_str = death_str.replace('%2$s', f' {zh_cn_data[death_cause_person]} ')
        else:
            player_id2 = get_id_by_mc_username(death_cause_person)
            if player_id2:
                death_str = death_str.replace('%2$s', f' `{death_cause_person}` ({get_tg_username_by_id(player_id2)}) ')
            else:
                death_str = death_str.replace('%2$s', f' `{death_cause_person}` ')
        if death_cause:
            death_str = death_str.replace('%3$s', f' `{death_cause}` ')
    send_message(death_str)


@sio.on('chat', namespace='/message')
def on_message(data):
    logger.info({'收到 chat 事件', data})
    data_json = json.loads(data)
    player_name = data_json['sender']['minecraft_name']
    player_id = get_id_by_mc_username(player_name)

    if get_tg_username_by_id(player_id):
        message_str = f'`{player_name}` ({get_tg_username_by_id(player_id)})：'
    else:
        message_str = f'`{player_name}`：'
    reply_id = None
    return_message = ''
    is_mentioned = False

    # 复制 message 模板
    message_to_send = copy.deepcopy(message_template)

    message_to_send['sender']['minecraft_name'] = player_name
    message_to_send['sender']['telegram_name'] = get_tg_username_by_id_noformat(
        get_id_by_mc_username(player_name)) or 'UNBOUND'
    message_to_send['sender']['telegram_id'] = get_id_by_mc_username(player_name) or 0

    for message_content in data_json['message']['content']:
        if message_content['type'] == 'text':
            xaero_waypoint_pattern = r'xaero-waypoint:(.*?):(.*?):(\S+):(\S+):(\S+):.*?:.*?:.*?:(\S+)'
            xaero_waypoint_match = re.search(xaero_waypoint_pattern, message_content['content'])

            if xaero_waypoint_match:
                fullname = xaero_waypoint_match.group(1)
                single = xaero_waypoint_match.group(2)
                x = xaero_waypoint_match.group(3)
                y = xaero_waypoint_match.group(4)
                z = xaero_waypoint_match.group(5)
                world = xaero_waypoint_match.group(6)

                if world == 'Internal-overworld-waypoints':
                    world = '主世界'
                elif world == 'Internal-the-nether-waypoints':
                    world = '下界'
                elif world == 'Internal-the-end-waypoints':
                    world = '末地'
                else:
                    world = tg_escape(world)

                if fullname == 'gui.xaero-deathpoint':
                    fullname = '上次死亡地点'
                elif fullname == 'gui.xaero-deathpoint-old':
                    fullname = '此前死亡地点'

                message_str += f'分享了一个来自 {world} 的名为 *{tg_escape(fullname)}*({tg_escape(single)}) 的路径点 `({x}, {y}, {z})`'
                return_message += f'分享了一个来自 {world} 的名为 *{fullname}*({single}) 的路径点 `({x}, {y}, {z})`'
            else:
                message_str += tg_escape(message_content['content'])
                return_message += message_content['content']
        elif message_content['type'] == 'at':
            tg_id = message_content['id']
            if tg_id == 0:
                return  # 如果要@的tg id是0就不处理
            userinfo = bot.get_chat(tg_id)
            tg_username = userinfo.username
            if tg_username:
                tg_username = tg_escape(tg_username)
                message_str += f'@{tg_username} '
            else:
                tg_username = tg_escape(userinfo.first_name)
                message_str += f' [@{tg_username}](tg://user?id={tg_id}) '
            message_to_send['message']['content'].append({
                'type': 'at',
                'id': tg_id,
                'content': tg_username,
            })
            is_mentioned = True

        elif message_content['type'] == 'reply':
            reply_id = message_content['id']

    if reply_id:
        sent_message = bot.send_message(group_id, message_str, reply_to_message_id=reply_id,
                                        disable_web_page_preview=True)

        # logger.info(sent_message)

        content_type_zh = {
            'photo': '图片',
            'video': '视频',
            'audio': '音频',
            'voice': '语音',
            'sticker': '贴纸',
            'document': '文件',
        }

        reply_str = ''

        if sent_message.reply_to_message.content_type == 'text':
            reply_str = sent_message.reply_to_message.text
        # 判断是否在列表中
        elif sent_message.reply_to_message.content_type in content_type_zh.keys():
            reply_str = '[' + content_type_zh[sent_message.reply_to_message.content_type] + ']'

            if sent_message.reply_to_message.content_type == 'photo':
                file = bot.get_file(sent_message.reply_to_message.photo[-1].file_id)
                reply_str += ' (' + file.file_path + ')'
            elif sent_message.reply_to_message.content_type == 'video':
                reply_str += ' (' + sent_message.reply_to_message.video.file_name + ')'
            elif sent_message.reply_to_message.content_type == 'audio':
                reply_str += ' (' + sent_message.reply_to_message.audio.file_name + ')'
            elif sent_message.reply_to_message.content_type == 'document':
                reply_str += ' (' + sent_message.reply_to_message.document.file_name + ')'
            elif sent_message.reply_to_message.content_type == 'sticker':
                reply_str += ' ' + sent_message.reply_to_message.sticker.emoji

            if sent_message.reply_to_message.caption:
                reply_str += ' ' + sent_message.reply_to_message.caption

        message_to_send['message']['id'] = sent_message.message_id
        message_to_send['message']['content'].extend([{
            'type': 'reply',
            'id': reply_id,
            'content': reply_str,
        }, {
            'type': 'text',
            'id': sent_message.message_id,
            'content': return_message,
        }])
        sio.emit('chat', message_to_send, namespace='/message')
        logger.info({'return to server (reply)', reply_id, return_message})
    else:
        # print(group_id, message_str)
        sent_message = bot.send_message(group_id, message_str, disable_web_page_preview=True)
        message_to_send['message']['id'] = sent_message.message_id
        if is_mentioned:
            message_to_send['message']['content'].append({
                'type': 'text',
                'id': sent_message.message_id,
                'content': return_message,
            })
            sio.emit('chat', message_to_send, namespace='/message')
            logger.info({'return to server (send)', message_str, return_message})


@sio.on('advancement', namespace='/message')
def on_message(data):
    logger.info({'收到 advancement 事件', data})
    data_json = json.loads(data)
    player_name = data_json['sender']['minecraft_name']
    player_id = get_id_by_mc_username(player_name)

    logger.info(f'{player_name} 成就 {data_json["message"]["content"]}')

    advancement_dict = data_json["message"]["content"]
    advancement_format = advancement_dict[0]['content']
    advancement_title = advancement_dict[1]['content']
    advancement_description = advancement_dict[2]['content']

    # 读取res/zh_cn.json
    zh_cn_data = read_data('zh_cn', 'res')
    # 获取advancement_format对应的值
    advancement_format_value = zh_cn_data[advancement_format]
    if player_id:
        adv_str = advancement_format_value % (
            f'`{player_name}` ({get_tg_username_by_id(player_id)}) ', f" \[*{zh_cn_data[advancement_title]}*]")
        adv_str += f'\n —— _{zh_cn_data[advancement_description]}_'
        send_message(adv_str)
    else:
        adv_str = advancement_format_value % (f'`{player_name}` ', f" \[*{zh_cn_data[advancement_title]}*]")
        adv_str += f'\n —— _{zh_cn_data[advancement_description]}_'
        send_message(adv_str)


@sio.on('players', namespace='/status')
def on_message(data):
    logger.info({'收到 players 事件', data})
    data_json = json.loads(data)
    res_str = f'当前在线玩家数: {str(data_json["current"])} / {str(data_json["maximum"])}'
    # 判断玩家列表是否为空
    if len(data_json['players']) > 0:
        res_str += '\n玩家列表:\n'
        players_str = ''
        for player in data_json['players']:
            player_id = get_id_by_mc_username(player['name'])
            if player_id:
                players_str = set_str_if_empty(players_str,
                                               f'`{player["name"]}` ({get_tg_username_by_id(player_id)})',
                                               ', ')
            else:
                players_str = set_str_if_empty(players_str, '`' + player["name"] + '`', ', ')
        res_str += players_str
    send_message(res_str)


@sio.on('performance', namespace='/status')
def on_message(data):
    logger.info({'收到 performance 事件', data})
    data_json = json.loads(data)
    res_str = f'TPS: {str(round(data_json["tps"], 3))}\n' \
              f'MSPT: {str(round(data_json["mspt"], 3))}\n'
    send_message(res_str)


@sio.on('*', namespace='/status')
def catch_all(event, data):
    logger.info({'status 收到更多事件', event, data})


@sio.on('*', namespace='/message')
def catch_all(event, data):
    logger.info({'message 收到更多事件', event, data})


@sio.event(namespace='/status')
def connect():
    logger.info("status 已连接")


@sio.event(namespace='/message')
def connect():
    logger.info("message 已连接")


@sio.event(namespace='/status')
def connect_error(data):
    logger.error({'status 连接出错', data})


@sio.event(namespace='/message')
def connect_error(data):
    logger.error({'message 连接出错', data})


@sio.event(namespace='/status')
def disconnect():
    logger.error("status 断开连接")


@sio.event(namespace='/message')
def disconnect():
    logger.error("message 断开连接")


ws_url = config['websocket_url']
sio.connect(ws_url, namespaces=['/status', '/message'])
