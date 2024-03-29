import configparser
import time
import datetime
import gspread
import os
import sys
import logging
import logging.handlers
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# 設定ファイル
SETTING_DIR = 'settings'

dir_path = f'{os.path.dirname(os.path.abspath(sys.argv[0]))}/{SETTING_DIR}'

ini_file = configparser.ConfigParser()
ini_file.read(f'{dir_path}/config.ini', 'UTF-8')
WORKBOOK_KEY = ini_file.get('SPREAD-SHEETS', 'WORKBOOK_KEY')

# ログの設定
# ログディレクトリのパス
LOG_DIR = "logs"
log_dir_path = f"{os.path.dirname(os.path.abspath(sys.argv[0]))}/{LOG_DIR}"
os.makedirs(LOG_DIR, exist_ok=True)
# ログフォーマットを設定
log_format = "%(asctime)s [%(levelname)s]: %(message)s"
logging.basicConfig(format=log_format, level=logging.INFO)
# ログファイル名に現在の日時を含む
current_date = datetime.datetime.now().strftime("%Y%m%d%H%M")
log_file = os.path.join(log_dir_path, f"Stockwatcher_by_scraping_{current_date}.log")
# ログファイルのローテーション（1週間以上前のログファイルを削除）
one_week_ago = datetime.datetime.now() - datetime.timedelta(days=6)
for filename in os.listdir(log_dir_path):
    file_path = os.path.join(log_dir_path, filename)
    if filename.endswith(".log"):
        log_date_str = filename.split("_")[3].split(".")[0]
        log_date = datetime.datetime.strptime(log_date_str, "%Y%m%d%H%M")
        if log_date <= one_week_ago:
            os.remove(file_path)
# ログファイルハンドラを追加
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(log_format))
# ルートロガーにハンドラを追加
root_logger = logging.getLogger()
root_logger.addHandler(file_handler)

def operate_sheet(mode, data = ''):

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(f'{dir_path}/service_account.json', scope)
    gc = gspread.authorize(credentials)

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

        logging.info('スプレッドシートへの入力が完了しました。')

def get_data(asins):

    # WebDriverの初期化
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = webdriver.Chrome(options=options)
    driver.set_window_position(0,0) # ブラウザの位置を左上に固定
    driver.set_window_size(860,1200) # ブラウザのウィンドウサイズを固定

    data = {}

    for asin in asins:
        retry_count = 0
        max_retries = 2
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
                if len(driver.find_elements(By.CSS_SELECTOR, "#add-to-cart-button")):
                    add_to_cart_button = driver.find_element(By.CSS_SELECTOR, "#add-to-cart-button")
                else:
                    add_to_cart_button = driver.find_element(By.CSS_SELECTOR, "#add-to-cart-button-ubb")
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
                    logging.info('キャンペーン広告をクリックしました。ブラウザバックします')
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
                logging.info(f"ASIN: {asin} - 購入可能数量: {available_quantity}")

                data[asin] = available_quantity
                is_success = True

            except Exception as e:
                if retry_count > max_retries:
                    logging.error(e)
                    logging.error(f'{asin} のデータ取得のリトライ上限に達しました。次の商品に移ります。')
                    data[asin] = 'error'
                    break
                else:
                    retry_count += 1
                    logging.warning(f'{asin} のデータ取得に失敗しました。リトライします。（リトライ回数：{retry_count}回目）')
            finally:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[-1])

    # WebDriverを閉じる
    driver.quit()
    logging.info('データの取得が完了しました。')
    return data

def main_func():
    try:
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
        logging.info(f'処理時間：{round(tim, 2)}秒')
    except Exception as e:
        logging.error('エラー発生：')
        logging.error(e)

if __name__ == '__main__':

    main_func()
