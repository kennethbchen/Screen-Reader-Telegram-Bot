import time
import random
import configparser
import json
import numpy as np
from PIL import ImageGrab
from PIL import Image
import pytesseract
import os
import cv2
import win32gui

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

config = configparser.ConfigParser()
try:
    if os.path.exists('config.ini'):
        config.read('config.ini')
        print("Config Loaded")
    else:
        raise IOError
except IOError:
    print("Config Not Found! Generating Config...")
    template = open("config_template.ini")
    file = open("config.ini", "w+")
    file.write(str(template.read()))
    file.close()

    print("Add Parameters and relaunch!")
    quit()

# Load Telegram Info
token = config['Telegram Info']['token']
group_chat_id = config['Telegram Info']['group_chat_id']

# Load General Config
pytesseract.pytesseract.tesseract_cmd = config['General']['tesseract_path']
debug_mode = False
if config['General']['debug_mode'] == "True":
    debug_mode = True
cycle_time = int(config['General']['cycle_time'])
rest_hours = str(config['General']['rest_hours']).split(',')

# Load Box Fine Tuning Config
scale_factor = float(config['Bounding Box Fine Tuning']['scale_factor'])
x1_tuning = float(config['Bounding Box Fine Tuning']['x1_tuning'])
y1_tuning = float(config['Bounding Box Fine Tuning']['y1_tuning'])
x2_tuning = float(config['Bounding Box Fine Tuning']['x2_tuning'])
y2_tuning = float(config['Bounding Box Fine Tuning']['y2_tuning'])

# Load Dialog Config
mapping = json.loads(config['Dialog']['mapping'])
dialog_notif = str(config['Dialog']['dialog_notif']).split("```")
dialog_fail = str(config['Dialog']['dialog_fail']).split("```")

updater = Updater(token, use_context=True)

shut_up = False
shh = False


def process_image(box, debug=False):
    screen = ImageGrab.grab(bbox=box)

    screen_numpy = np.array(screen)
    screen_numpy = cv2.cvtColor(screen_numpy, cv2.COLOR_BGR2GRAY)

    filename = "{}.png".format(os.getpid())
    cv2.imwrite(filename, screen_numpy)
    found_text = pytesseract.image_to_string(Image.open(filename), lang='eng', config='--psm 10')

    if debug:
        cv2.imshow('Debug', screen_numpy)
        print(found_text)
        while True:
            if cv2.waitKey(25) & 0xFF == ord('q'):
                cv2.destroyAllWindows()
                break
    os.remove(filename)
    return found_text


def get_window_bounds():
    window = win32gui.GetForegroundWindow()
    window_rect = win32gui.GetWindowRect(window)

    bot_offset = 12
    left_offset = 12
    right_offset = 12
    top_offset = 55
    adj_rect = ((window_rect[0] * scale_factor) + left_offset, (window_rect[1] * scale_factor) + top_offset,
                (window_rect[2] * scale_factor) - right_offset, (window_rect[3] * scale_factor) - bot_offset)

    return adj_rect


def crop_rect(rect):
    x, y, x2, y2 = rect
    w = x2 - x
    h = y2 - y

    output = x + w * x1_tuning, y + h * y1_tuning, x2 - w * x2_tuning, y2 - h * y2_tuning
    return output


def get_name():
    game_name = process_image(crop_rect(get_window_bounds()), debug=debug_mode)
    if game_name in mapping:
        return mapping[game_name]
    else:
        return ""


def generate_message():
    name = get_name()
    if name == "":
        return str(random.choice(tuple(dialog_fail)))
    else:
        return str(random.choice(tuple(dialog_notif))).format(name)


def cycle(cycle_time_val):
    global shut_up
    global shh
    start = time.time()
    cycle_text_time = time.time()
    current_day = time.localtime().tm_mday
    current_hour = time.localtime().tm_hour


    while True:
        if time.time() - cycle_text_time >= 60:
            cycle_text_time = time.time()
            print("Running {} {}...".format(time.localtime().tm_hour, time.localtime().tm_min))

        if shh and time.localtime().tm_mday is not current_day:
            shh = False
            current_day = time.localtime().tm_mday

        if time.time() - start >= cycle_time and not shut_up and not shh:
            start = time.time()
            rest_time = False
            for t in rest_hours:
                if current_hour == int(t):
                    print("Rest Hour '" + t + "' - Notification Skipped")
                    rest_time = True

            if not rest_time:
                text = generate_message()
                updater.bot.send_message(group_chat_id, generate_message())


def notify_command(update, context):
    update.message.reply_text(generate_message())


def shut_up_command(update, context):
    global shut_up
    if shut_up:
        update.message.reply_text("Hey! I got it the first time.")
    else:
        shut_up = True
        update.message.reply_text("Fine, I wont bother you anymore.")


def un_shut_up_command(update, context):
    global shut_up
    global shh
    if shut_up:
        shut_up = False
        shh = False
        update.message.reply_text("Did you miss me?")
    else:
        update.message.reply_text("You told me that already.")


def config_command(update, context):
    output = ""
    for section in config.sections():
        if not section == "Telegram Info":
            output += "[" + section + "] \n"
            for value in config[section]:
                if value is not "token" or value is not "group_chat_id":
                    output += value + " = " + config[section][value] + "\n"
            output += "\n"
    output += "[Vars]\n"
    output += "shut_up = " + str(shut_up) + "\n"
    output += "shh = " + str(shh)
    update.message.reply_text(output)


def shh_command(update, context):
    global shh
    if shh:
        update.message.reply_text("Hey! I got it the first time.")
    else:
        shh = True
        update.message.reply_text("Fine, I won't bother you until tomorrow.")


def unshh_command(update, context):
    global shh
    global shut_up

    if shh:
        shh = False
        shut_up = False
        update.message.reply_text("Did you miss me?")
    else:
        update.message.reply_text("You already told me that.")


def main():
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("notify", notify_command))
    dp.add_handler(CommandHandler("shutup", shut_up_command))
    dp.add_handler(CommandHandler("unshutup", un_shut_up_command))
    dp.add_handler(CommandHandler("config", config_command))
    dp.add_handler(CommandHandler("shh", shh_command))
    dp.add_handler(CommandHandler("unshh", unshh_command))

    updater.start_polling()
    cycle(int(cycle_time))


if __name__ == '__main__':
    main()
