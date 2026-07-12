import discord
from discord.ext import commands
import random
import os
from supabase import create_client, Client

# 設定 intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 初始化機器人
bot = commands.Bot(command_prefix='!', intents=intents)

# 遊戲狀態管理
game_state = {
    "is_playing": False,
    "players": []
}

# --- Supabase 雲端資料庫設定 ---
# 這裡建議使用環境變數（Environment Variables），部署到 Render 時會設定
SUPABASE_URL = os.environ.get("SUPABASE_URL", "你的_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "你的_SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def load_words_from_cloud():
    """從雲端資料庫讀取所有題庫"""
    try:
        response = supabase.table("word_bank").select("word1, word2").execute()
        # 將格式轉換為 [["詞A", "詞B"], ["詞C", "詞D"]]
        return [[row["word1"], row["word2"]] for row in response.data]
    except Exception as e:
        print(f"資料庫讀取失敗：{e}")
        return [["滷肉飯", "爌肉飯"]] # 備用防壞底線

@bot.event
async def on_ready():
    print(f'機器人已上線：{bot.user}')
    # 測試連線
    words = load_words_from_cloud()
    print(f'已成功從雲端資料庫載入 {len(words)} 組題庫！')

@bot.command()
async def join(ctx):
    """加入遊戲"""
    if game_state["is_playing"]:
        await ctx.send("遊戲已經開始了，請等下一局！")
        return
    if ctx.author in game_state["players"]:
        await ctx.send(f"{ctx.author.mention} 你已經在遊戲中了！")
        return
    if len(game_state["players"]) >= 10:
        await ctx.send("房間已滿 (最多 10 人)！")
        return
        
    game_state["players"].append(ctx.author)
    await ctx.send(f"{ctx.author.mention} 加入了遊戲！目前人數：{len(game_state['players'])}/10")

@bot.command()
async def leave(ctx):
    """退出遊戲"""
    if game_state["is_playing"]:
        await ctx.send("遊戲進行中，無法退出！")
        return
    if ctx.author in game_state["players"]:
        game_state["players"].remove(ctx.author)
        await ctx.send(f"{ctx.author.mention} 退出了遊戲。目前人數：{len(game_state['players'])}")

@bot.command()
async def status(ctx):
    """查看目前房間人數"""
    if not game_state["players"]:
        await ctx.send("目前房間沒有人。")
        return
    player_names = [p.display_name for p in game_state["players"]]
    await ctx.send(f"目前玩家 ({len(player_names)}人): {', '.join(player_names)}")

@bot.command()
async def start(ctx):
    """開始遊戲並分配身分與詞彙"""
    if game_state["is_playing"]:
        await ctx.send("遊戲已經在進行中了！")
        return
    player_count = len(game_state["players"])
    if player_count < 3:
        await ctx.send(f"人數不足！至少需要 3 人才能玩，目前只有 {player_count} 人。")
        return
        
    game_state["is_playing"] = True
    await ctx.send("遊戲開始！正在私訊分配詞彙...")

    # 每次開始遊戲都從雲端撈取最新題庫，確保即時同步
    word_bank = load_words_from_cloud()
    word_pair = random.choice(word_bank)
    words = list(word_pair)
    random.shuffle(words)
    good_word, spy_word = words[0], words[1]

    roles = ["臥底"]
    if player_count >= 5:
        roles.append("白板")
    if player_count >= 8:
        roles.append("臥底")

    while len(roles) < player_count:
        roles.append("好人")
        
    random.shuffle(roles)

    for i, player in enumerate(game_state["players"]):
        role = roles[i]
        try:
            if role == "好人":
                await player.send(f"🕵️‍♂️ 你的身分是：**【好人】**\n📝 你的詞彙是：**{good_word}**")
            elif role == "臥底":
                await player.send(f"🕵️‍♂️ 你的身分是：**【臥底】**\n📝 你的詞彙是：**{spy_word}**")
            elif role == "白板":
                await player.send(f"🕵️‍♂️ 你的身分是：**【白板】**\n📝 你的詞彙是：**(無)**")
        except discord.Forbidden:
            await ctx.send(f"⚠️ 無法私訊 {player.mention}，請確認是否關閉了伺服器私訊功能！遊戲中止。")
            game_state["is_playing"] = False
            return

    await ctx.send("✅ 所有身分與詞彙已發送完畢！請大家開始第一輪描述！")

@bot.command()
async def end(ctx):
    """結束並重置遊戲"""
    game_state["is_playing"] = False
    game_state["players"] = []
    await ctx.send("🛑 遊戲已結束，房間已清空。輸入 `!join` 可以開啟下一局！")

@bot.command()
async def add(ctx, word1: str = None, word2: str = None):
    """新增題目並永久儲存到雲端資料庫"""
    if word1 is None or word2 is None:
        await ctx.send("⚠️ 格式錯誤！請輸入：`!add [好人詞] [臥底詞]`")
        return

    current_words = load_words_from_cloud()
    if [word1, word2] in current_words or [word2, word1] in current_words:
        await ctx.send(f"⚠️ 題庫裡已經有 **{word1}** 與 **{word2}** 囉！")
        return

    try:
        # 直接寫入雲端
        supabase.table("word_bank").insert({"word1": word1, "word2": word2}).execute()
        await ctx.send(f"✅ 成功新增並儲存至雲端：**{word1}** vs **{word2}**！")
    except Exception as e:
        await ctx.send(f"❌ 雲端儲存失敗，請聯絡管理員。")

# 這樣寫的話，本機測試如果沒有設定環境變數，就會去讀取後面那串預備 Token；
# 部署到 Render 時，Render 會自動用最安全的雲端環境變數覆蓋它。
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
bot.run(DISCORD_TOKEN)
