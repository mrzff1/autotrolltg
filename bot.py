from telethon import TelegramClient, events # pip install telethon
import asyncio
import os
import json
import random
from ollama import Client # pip install ollama
import datetime

# # # # # # # # #
# ИНИЦИАЛИЗАЦИЯ #
# # # # # # # # #

client = Client(host='http://localhost:11434') # адрес сервера ollama, по умолчанию 11434

# заполните profile.json своими данными (создайте приложение на https://my.telegram.org и скопируйте API_ID и API_HASH)
def load_profile(filepath='profile.json'):
    with open(filepath, 'r') as file:
        data = json.load(file)
    if data['API_ID'] and data['API_HASH']: return data['API_ID'], data['API_HASH']
    raise TypeError('API token was not created')

API_ID, API_HASH = load_profile()
SESSION_FILE = 'profile.session' # файл БД sqlite3, закрывайте скрипт в терминале через ctrl+c вместо ctrl+z, иначе БД умрет


# # # # # # # # #
# КОНФИГУРАЦИЯ  #
# # # # # # # # #

class config:
    __cfg = json.load(open('config.json', 'r'))
    saturn_prompt = __cfg['saturn.prompt']
    saturn_model = __cfg['saturn.model']
    smartsystem_prompt = __cfg['smartsystem.prompt']
    smartsystem_model = __cfg['smartsystem.model']
    mercury_model = __cfg['mercury.model']
    mercury_prompt = __cfg['mercury.prompt']
    automsg_default = __cfg['automsg_mini.default']
    ignore_bots = __cfg['ignore_bots'] # игнорировать ли ботов, будет игнорировать даже пользователей с окончанием bot в нике
    ignore_replies = __cfg['ignore_replies']
    context_length = int(__cfg['context_length']) # сколько сообщений помнить боту
    whitelist_add = __cfg['whitelist.add']
    whitelist_remove = __cfg['whitelist.remove']
    

# # # # # # # # # # # #
# КЛАССЫ ГЕНЕРАТОРОВ  #
# # # # # # # # # # # #

class saturn:
    @staticmethod
    def generate(chat):
        messages = [{'role': 'system', 'content': config.saturn_prompt}] + chat
        result = client.chat(model=config.saturn_model, messages=messages)
        return result


class smartsystem:
    @staticmethod
    def generate(chat):
        messages = [{'role': 'system', 'content': config.smartsystem_prompt}] + chat
        result = client.chat(model=config.smartsystem_model, messages=messages)
        return result


class automsg_mini: # заполните faq подходящими фразами либо возьмите готовый (мало строк) с репозитория
    @staticmethod
    def generate(request, case_sensitive=False, show_details=False):
        if random.randint(0, 1): return config.automsg_default
        file_path = 'faq.txt'
        with open(file_path, 'r') as file:
            faq = file.read().split('\n')
        return random.choice(faq)

class mercury: # классификатор сообщений
    @staticmethod
    def simplegen(chat):
        a = random.randint(1,3)
        if a == 1: return saturn.generate(chat)
        elif a == 2: return smartsystem.generate(chat)
        else: return {'message':{'content':automsg_mini.generate(chat[-1]['content'])}}
    
    @staticmethod
    def smartgen(chat): # выбор через ии-фильтр
        result = client.chat(model=config.mercury_model, messages=[{
         'role': 'user',
         'content': config.mercury_prompt + chat[-1]['content']}])
        try: 
            score = int(result['message']['content'])
            if score >= 7: return saturn.generate(chat)
            elif 5 < score < 7: return smartsystem.generate(chat)
            else: return {'message':{'content':automsg_mini.generate(chat[-1]['content'])}}
        except: return mercury.simplegen(chat) # если нейросеть выдала не число (за сотни тестов такого не происходило), будет случайный выбор


# # # # # # # # # # # #
# ХРАНЕНИЕ КОНТЕКСТА  #
# # # # # # # # # # # #

class context:
    @staticmethod
    def load(uid): # загрузка контекста из json
        try:
            with open('history.json', 'r') as file: chats = json.load(file)
            return chats[uid]
        except: return []
    
    @staticmethod
    def save(uid, chat): # сохранение контекста и создание файла при необходимости
        try:
            with open('history.json', 'r') as file: chats = json.load(file)
            chats[uid] = chat
        except: chats = {uid:chat}
        with open('history.json', 'w') as file: json.dump(chats, file)
        
    @staticmethod
    def clear(uid): # сброс контекста по желанию пользователя
        try:
            with open('history.json', 'r') as file: chats = json.load(file)
            chats[uid] = []
        except: chats = []
        with open('history.json', 'w') as file: json.dump(chats, file)


# # # # # # # # #
# БЕЛЫЙ СПИСОК  #
# # # # # # # # #

class whitelist:
    @staticmethod
    def add(uid): # добавление в белый список
        wlist = whitelist.get()
        if str(uid) in wlist: return
        wlist.append(str(uid))
        with open('whitelist.json', 'w') as file: json.dump(wlist, file)
    
    @staticmethod
    def get():
        try:
            with open('whitelist.json', 'r') as file: wlist = json.load(file)
            return wlist
        except: return []
    
    @staticmethod
    def remove(uid):
        wlist = whitelist.get()
        wlist.remove(str(uid))
        with open('whitelist.json', 'w') as file:
            json.dump(wlist, file)
    
async def main(): # работа с запросами
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    
    await client.start()
    print("Бот запущен!")

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def handle_new_message(event):
        if event.out: return
        try:
            sender = await event.get_sender()
            if config.ignore_replies and sender.first_name == 'Replies': return # ответы в группах считаются личными сообщениями, но ответить напрямую на них нельзя (403)
            if sender.username:
                if config.ignore_bots and sender.username[-3:] == 'bot': return
            if str(sender.id) in whitelist.get(): return
            chat = context.load(str(sender.id)) # получаем объект чата
            chat.append({'role':'user', 'content': f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {event.message.message}"})
            result = mercury.smartgen(chat)
            response_text = result['message']['content']
            await event.reply(response_text)
            chat.append({'role':'bot', 'content': response_text})
            context.save(str(sender.id), chat[-config.context_length:])
        except Exception as e: print(e)
    
    @client.on(events.NewMessage(incoming=False, func=lambda e: e.is_private))
    async def handle_my_message(event): # работа с системными командами
        try:
            sender = await event.get_sender()
            if event.message.message == '.whitelist':
                whitelist.add(event.message.peer_id.user_id)
                await event.reply(config.whitelist_add)
                return
            if event.message.message == '.removewl':
                whitelist.remove(event.message.peer_id.user_id)
                await event.reply(config.whitelist_remove)
                return
                
        except Exception as e: print(e)

    await client.run_until_disconnected()

if __name__ == '__main__': # тест на алкоголика
    asyncio.run(main())

