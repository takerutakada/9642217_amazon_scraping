import configparser
import time
import datetime
import gspread
import os
import sys
import logging
import logging.handlers
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# 設定ファイル
SETTING_DIR = 'settings_test_2'

dir_path = f'{os.path.dirname(os.path.abspath(sys.argv[0]))}/{SETTING_DIR}'

ini_file = configparser.ConfigParser()
ini_file.read(f'{dir_path}/config.ini', 'UTF-8')
WORKBOOK_KEY = ini_file.get('SPREAD-SHEETS', 'WORKBOOK_KEY')

# ログ取得 https://blog.hiros-dot.net/?p=10297 https://irukanobox.blogspot.com/2020/09/python.html
log = logging.getLogger(__name__)
# ログ出力レベルの設定
log.setLevel(logging.DEBUG)

# ローテーティングファイルハンドラを作成
rh = logging.handlers.RotatingFileHandler(
        r'./log/app.log',
        encoding='utf-8',
        maxBytes=100,
        backupCount=7
    )

# ロガーに追加
log.addHandler(rh)

log.debug('===== start =====')

for num in range(30):
    log.debug('debug:{}'.format(str(num)))

log.debug('===== end =====')

def operate_sheet(mode, data = ''):

    gc = gspread.oauth(
        credentials_filename = f'{dir_path}/client_secret.json',
        authorized_user_filename = f'{dir_path}/authorized_user.json',
        )

    # スプレッドシートを開く
    worksheet = gc.open_by_key(WORKBOOK_KEY).worksheet('シート1')

    if mode == 'r':
        return worksheet.col_values(1)[1:]

    elif mode == 'w':

        # 既存のデータを取得
        existing_data = worksheet.get_values()

        # 現在の日付を取得
        current_date = datetime.datetime.now().strftime("%Y/%m/%d")

        # 列名を取得
        header_row = worksheet.row_values(1)
        num_existing_columns = len(header_row)

        # 新しい列を追加
        new_column_index = num_existing_columns + 1
        worksheet.update_cell(1, new_column_index, current_date)

        # 各データに対して処理
        for asin, quantity in data.items():
            row_exists = False
            for row in existing_data:
                if row[0] == asin:
                    row_exists = True
                    row_index = existing_data.index(row) + 1
                    worksheet.update_cell(row_index, new_column_index, quantity)
                    break

            if not row_exists:
                new_row = [asin, ""] + [""] * (new_column_index - 2) + [quantity]
                worksheet.append_row(new_row)

        print('スプレッドシートへの入力が完了しました。')

def get_data(asins):

    # WebDriverの初期化
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.set_window_position(0,0) # ブラウザの位置を左上に固定
    driver.set_window_size(860,1200) # ブラウザのウィンドウサイズを固定

    data = {}

    for asin in asins:
        retry_count = 0
        max_retries = 4
        is_success = False
        while not is_success:
            try:
                # Amazon商品検索用URLを構築（&rh=p_...以降でスポンサー広告商品を除外）
                url = f"https://www.amazon.co.jp/s?k={asin}&rh=p_36%3A1000-%2Cp_8%3A0-&__mk_ja_JP=カタカナ&tag=krutw-22&ref=nb_sb_noss_1"

                driver.implicitly_wait(20 + retry_count * 10)

                # URLにアクセス
                driver.get(url)

                # 商品詳細ページに遷移
                product_link = driver.find_element(By.CSS_SELECTOR, ".s-result-item a")
                product_link.click()

                driver.implicitly_wait(20)

                driver.switch_to.window(driver.window_handles[-1])

                # カートに追加
                add_to_cart_button = driver.find_element(By.CSS_SELECTOR, "#add-to-cart-button")
                add_to_cart_button.click()

                driver.implicitly_wait(20)

                # カートに移動
                driver.get("https://www.amazon.co.jp/gp/cart/view.html")

                # 数量選択ページに遷移
                quantity_button = driver.find_element(By.CSS_SELECTOR, "#a-autoid-0-announce")

                driver.implicitly_wait(20)

                quantity_button.click()

                # 10+を選択
                while 'product' in driver.current_url:
                    print('キャンペーン広告をクリックしました。ブラウザバックします')
                    driver.back()
                ten_plus_option = driver.find_element(By.XPATH, "//a[contains(text(),'10+')]")

                driver.implicitly_wait(20)

                ten_plus_option.click()

                # 数量入力
                quantity_input = driver.find_element(By.NAME, "quantityBox")
                quantity_input.send_keys(Keys.CONTROL + "a")
                quantity_input.send_keys("999")
                quantity_input.send_keys(Keys.RETURN)
                time.sleep(3)

                driver.implicitly_wait(20)

                # 購入可能数量を取得して出力
                driver.get("https://www.amazon.co.jp/gp/cart/view.html")

                quantity_input = driver.find_element(By.NAME, "quantityBox")
                available_quantity = quantity_input.get_attribute("value")
                print(f"ASIN: {asin} - 購入可能数量: {available_quantity}")

                data[asin] = available_quantity
                is_success = True

            except Exception as e:
                if retry_count > max_retries:
                    print(e)
                    print(f'{asin} のデータ取得のリトライ上限に達しました。次の商品に移ります。')
                    data[asin] = 'error'
                    break
                else:
                    retry_count += 1
                    print(f'{asin} のデータ取得に失敗しました。リトライします。（リトライ回数：{retry_count}回目）')

    # WebDriverを閉じる
    driver.quit()
    print('データの取得が完了しました。')
    return data

def main_func():

    # 時間計測開始
    time_sta = time.perf_counter()
    # 実行
    asins = operate_sheet('r')
    data = get_data(asins)
    operate_sheet('w', data)
    # 時間計測終了
    time_end = time.perf_counter()
    # 経過時間（秒）
    tim = time_end- time_sta
    print(f'処理時間：{round(tim, 2)}秒')

if __name__ == '__main__':

    main_func()

