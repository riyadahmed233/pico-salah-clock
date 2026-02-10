from machine import Pin
import time
import network
import socket
import urequests
import struct
from picographics import PicoGraphics, DISPLAY_INKY_PACK
import config

display = PicoGraphics(display=DISPLAY_INKY_PACK)
led = Pin("LED", Pin.OUT)

button_a = Pin(12, Pin.IN, pull=Pin.PULL_UP)
button_b = Pin(13, Pin.IN, pull=Pin.PULL_UP)
button_c = Pin(14, Pin.IN, pull=Pin.PULL_UP)

WIDTH, HEIGHT = display.get_bounds()
display.set_update_speed(2)
display.set_font("sans")

NTP_DELTA = 2208988800
host = "uk.pool.ntp.org"
SSID = config.SSID
PWD = config.PWD

rtc = machine.RTC()

synced_today = False
drawn_on_change = True
current_state = 0
last_synced = [0, 0]
last_prayer_fetch_date = None


def connect(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    while wlan.isconnected() == False:
        print("Waiting for connection...")
        time.sleep(1)
    ip = wlan.ifconfig()[0]
    print(f"Connected on {ip}")


def is_daylight_savings(current_time):
    month = current_time[1]
    if month in [11, 12, 1, 2]:
        return False
    if month in [4, 5, 6, 7, 8, 9]:
        return True
    return False


def set_time():
    global synced_today
    NTP_QUERY = bytearray(48)
    NTP_QUERY[0] = 0x1B
    addr = socket.getaddrinfo(host, 123)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1)
        res = s.sendto(NTP_QUERY, addr)
        msg = s.recv(48)
    finally:
        s.close()
    val = struct.unpack("!I", msg[40:44])[0]
    t = val - NTP_DELTA
    tm = time.gmtime(t)
    is_bst = is_daylight_savings(tm)
    if not is_bst:
        rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
    else:
        rtc.datetime(
            (tm[0], tm[1], tm[2], tm[6] + 1, ((tm[3] + 1) % 24), tm[4], tm[5], 0)
        )
    synced_today = True


def get_salah_times(max_retries=3):
    for attempt in range(max_retries):
        try:
            connect(SSID, PWD)
            url = f"https://www.londonprayertimes.com/api/times/?format=json&key={config.APIKEY}&24hours=true"
            times = urequests.get(url).json()
            return [
                [int(x) for x in times["fajr"].split(":")],
                [int(x) for x in times["sunrise"].split(":")],
                [int(x) for x in times["dhuhr"].split(":")],
                [int(x) for x in times["asr_2"].split(":")],
                [int(x) for x in times["magrib"].split(":")],
                [int(x) for x in times["isha"].split(":")],
            ]
        except:
            if attempt < max_retries - 1:
                time.sleep(2)
    return [[5, 0], [6, 0], [12, 0], [16, 0], [18, 0], [20, 0]]


def get_next_salah(current_t, s_times):
    for s in s_times:
        if s[0] > current_t[0]:
            return s
        if s[0] == current_t[0]:
            if s[1] >= current_t[1]:
                return s
    return s_times[0]


def title_case(string):
    return string[0].upper() + string[1:]


def draw_clock(date, time, salah_times, next_salah, salah_names):
    global current_state, last_synced

    if current_state != 2:
        months = {
            1: "Jan",
            2: "Feb",
            3: "Mar",
            4: "Apr",
            5: "May",
            6: "Jun",
            7: "Jul",
            8: "Aug",
            9: "Sep",
            10: "Oct",
            11: "Nov",
            12: "Dec",
        }
        print_time = "{:02}:{:02}".format(time[0], time[1])
        print_date = "{:02} {}".format(date[2], months[date[1]])
        print_year = "{:04}".format(date[0])
        print_salah_time = "{:02}:{:02}".format(next_salah[0], next_salah[1])
        try:
            salah_time_str = ["{:02}:{:02}".format(i[0], i[1]) for i in salah_times]
            print_salah_name = title_case(
                str(
                    {
                        salah_time_str[i]: salah_names[i]
                        for i in range(len(salah_names))
                    }[print_salah_time]
                )
            )
        except:
            print_salah_name = "Fajr"

    def screen_0():
        time_scale = 2.8
        date_scale = 1
        year_scale = 1
        salah_time_scale = 1
        salah_name_scale = 0.8

        main_time_width = display.measure_text(print_time, time_scale)
        date_width = display.measure_text(print_date, date_scale)
        year_width = display.measure_text(print_year, year_scale)
        salah_time_width = display.measure_text(print_salah_time, salah_time_scale)
        salah_name_width = display.measure_text(print_salah_name, salah_name_scale)

        display.set_thickness(5)
        display.set_pen(15)
        display.clear()
        display.set_pen(5)
        display.line(0, 70, WIDTH, 70)
        display.line(WIDTH // 2, 75, WIDTH // 2, HEIGHT)
        display.set_pen(0)
        display.text(
            print_time, (WIDTH // 2) - (main_time_width // 2), 37, scale=time_scale
        )

        display.set_thickness(2)
        display.text(
            print_date,
            (WIDTH // 4) - (date_width // 2),
            87,
            scale=date_scale,
            spacing=1,
        )
        display.text(
            print_year, (WIDTH // 4) - (year_width // 2), 115, scale=year_scale
        )

        display.text(
            print_salah_time,
            (WIDTH - (WIDTH // 4)) - (salah_time_width // 2),
            115,
            scale=salah_time_scale,
        )
        display.text(
            print_salah_name,
            (WIDTH - (WIDTH // 4)) - (salah_name_width // 2),
            85,
            scale=salah_name_scale,
        )

        display.update()

    def screen_1():
        display.set_thickness(5)
        display.set_pen(15)
        display.clear()
        display.set_pen(5)
        display.line((WIDTH // 3), 5, (WIDTH // 3), (HEIGHT - 5))
        display.line(2 * (WIDTH // 3), 5, 2 * (WIDTH // 3), (HEIGHT - 5))
        display.line(5, (HEIGHT // 2), (WIDTH // 3) - 5, HEIGHT // 2)
        display.line((WIDTH // 3) + 5, HEIGHT // 2, (2 * (WIDTH // 3)) - 5, HEIGHT // 2)
        display.line((2 * (WIDTH // 3)) + 5, HEIGHT // 2, WIDTH - 5, HEIGHT // 2)

        salah_name_scale = 0.6
        salah_time_scale = 1
        salah_name_widths = []

        for i in salah_names:
            salah_name_widths.append(display.measure_text(i, salah_name_scale))

        salah_time_str = ["{:02}:{:02}".format(i[0], i[1]) for i in salah_times]

        xs = [WIDTH // 3, 2 * (WIDTH // 3), WIDTH]
        ys = [15, 80]

        display.set_pen(0)
        display.set_thickness(2)

        count = 0

        for x in range(1, 4):
            for y in ys:
                display.text(
                    salah_names[count],
                    (x * (WIDTH // 3) - (WIDTH // 6)) - (salah_name_widths[count] // 2),
                    y,
                    scale=salah_name_scale,
                )
                display.text(
                    salah_time_str[count],
                    (x * (WIDTH // 3) - (WIDTH // 6))
                    - (
                        display.measure_text(salah_time_str[count], salah_time_scale)
                        // 2
                    ),
                    y + 25,
                    scale=salah_time_scale,
                )
                count += 1

        display.update()

    def screen_2():
        display.set_thickness(5)
        display.set_pen(15)
        display.clear()
        display.set_pen(0)

        synced_str = "Synced: {:02}:{:02}".format(last_synced[0], last_synced[1])
        left_scale = 0.8
        display.set_thickness(2)

        display.text("London Prayer Clock", 0, 40, scale=left_scale)
        display.text(synced_str, 0, 80, scale=left_scale)

        display.update()

    if current_state == 0:
        screen_0()
    elif current_state == 1:
        screen_1()
    elif current_state == 2:
        screen_2()


def get_time():
    year, month, day, wd, hour, minute, second, _ = rtc.datetime()
    return [year, month, day], [hour, minute, second]


def button(pin):
    global \
        current_state, \
        drawn_on_change, \
        date, \
        clock_time, \
        salah_times, \
        next_salah, \
        last_synced, \
        last_prayer_fetch_date
    if current_state == 0:
        drawn_on_change = False
        if pin == button_b:
            display.set_update_speed(1)
            current_state = 1
        if pin == button_c:
            current_state = 2
    elif current_state == 1:
        drawn_on_change = False
        if pin == button_a:
            current_state = 0
            display.set_update_speed(2)
        if pin == button_c:
            current_state = 2
            display.set_update_speed(2)
    elif current_state == 2:
        if pin == button_b:
            date, clock_time = get_time()
            last_prayer_fetch_date = date
            salah_times = get_salah_times()
            next_salah = get_next_salah(clock_time, salah_times)
            last_synced = clock_time
            draw_clock(date, clock_time, salah_times, next_salah, salah_names)

        if pin == button_c:
            display.set_update_speed(2)
            drawn_on_change = False
            current_state = 0


button_a.irq(trigger=Pin.IRQ_FALLING, handler=button)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button)


date, clock_time = [1, 1, 1], [0, 0, 0]
salah_times = [[0, 0] for _ in range(6)]
next_salah = [0, 0]
last_synced = [0, 0, 0]


def sync():
    global synced_today, date, clock_time
    connect(SSID, PWD)
    while synced_today == False:
        try:
            set_time()
        except:
            pass
    date, clock_time = get_time()


def main():
    global \
        synced_today, \
        current_state, \
        drawn_on_change, \
        date, \
        clock_time, \
        salah_times, \
        next_salah

    salah_names = ["Fajr", "Sunrise", "Zuhr", "Asr", "Maghrib", "Isha"]

    draw_clock([1, 1, 1], [0, 0, 0], [[0, 0] for _ in range(6)], [0, 0], salah_names)

    sync()

    last_prayer_fetch_date = date
    salah_times = get_salah_times()
    next_salah = get_next_salah(clock_time, salah_times)

    draw_clock(date, clock_time, salah_times, next_salah, salah_names)
    while True:
        time.sleep(0.01)
        date, clock_time = get_time()
        if current_state == 0:
            if drawn_on_change == False:
                draw_clock(date, clock_time, salah_times, next_salah, salah_names)
                drawn_on_change = True
            if clock_time[-1] == 0:
                if date != last_prayer_fetch_date:
                    last_prayer_fetch_date = date
                    salah_times = get_salah_times()
                next_salah = get_next_salah(clock_time, salah_times)
                draw_clock(date, clock_time, salah_times, next_salah, salah_names)
                if synced_today == False:
                    set_time()
        if current_state == 1 or current_state == 2:
            if drawn_on_change == False:
                draw_clock(date, clock_time, salah_times, next_salah, salah_names)
                drawn_on_change = True
        if clock_time == [0, 0, 5]:
            synced_today = False
            sync()


main()
