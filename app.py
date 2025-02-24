import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import os
import datetime
import re
import requests
from typing import Dict, Optional

# Constants
API_PHAT_NGUOI = "https://api.checkphatnguoi.vn/phatnguoi"
DATA_FILE = "registered_plates.json"
MAX_PLATES = 4

class VehicleBot(commands.Bot):
    """Bot chính để xử lý các lệnh kiểm tra phạt nguội"""
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='/', intents=intents)
        self.data_manager = DataManager(DATA_FILE)
        
    async def setup_hook(self):
        """Khởi tạo bot và sync commands"""
        await self.tree.sync()
        self.check_violations.start()
        print("✅ Bot đã sẵn sàng!")

class DataManager:
    """Quản lý dữ liệu biển số"""
    def __init__(self, filename: str):
        self.filename = filename
        self.data: Dict[str, int] = {}
        self.load_data()

    def load_data(self) -> None:
        """Đọc dữ liệu từ file"""
        if os.path.exists(self.filename):
            with open(self.filename, 'r', encoding='utf-8') as f:
                self.data = json.load(f)

    def save_data(self) -> None:
        """Lưu dữ liệu ra file"""
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

class VehicleCommands(commands.GroupCog, name="vehicle"):
    """Các lệnh xử lý biển số xe"""
    def __init__(self, bot: VehicleBot):
        self.bot = bot
        super().__init__()

    async def check_violation(self, plate: str) -> str:
        """Kiểm tra vi phạm từ API"""
        try:
            response = requests.post(API_PHAT_NGUOI, json={"bienso": plate})
            data = response.json()

            if "error" in data:
                return f"❌ {data['error']}"

            if "data" not in data or not isinstance(data["data"], list):
                return f"✅ Biển số {plate} chưa phát hiện vi phạm."

            embed = discord.Embed(
                title=f"🚗 Kết quả kiểm tra biển số {plate}",
                color=discord.Color.blue()
            )

            for item in data["data"]:
                embed.add_field(
                    name="Thông tin vi phạm",
                    value=(
                        f"🔹 Loại xe: {item.get('Loại phương tiện', 'N/A')}\n"
                        f"⏰ Thời gian: {item.get('Thời gian vi phạm', 'N/A')}\n"
                        f"📍 Địa điểm: {item.get('Địa điểm vi phạm', 'N/A')}\n"
                        f"⚠️ Vi phạm: {item.get('Hành vi vi phạm', 'N/A')}\n"
                        f"{'🟥' if item.get('Trạng thái') == 'Chưa xử phạt' else '🟩'} "
                        f"Trạng thái: {item.get('Trạng thái', 'N/A')}"
                    ),
                    inline=False
                )

            return embed

        except Exception as e:
            return f"⚠️ Lỗi: {str(e)}"

    @app_commands.command(name="check", description="Kiểm tra vi phạm của biển số")
    async def check(self, interaction: discord.Interaction, plate: str):
        """Kiểm tra vi phạm"""
        await interaction.response.defer()

        plate = re.sub(r'\s+|[^a-zA-Z0-9]', '', plate.strip().upper())
        if not re.match(r'^\d{2}[A-Z]{1,2}\d{5,6}$', plate):
            await interaction.followup.send("⚠️ Biển số không đúng định dạng!", ephemeral=True)
            return

        result = await self.check_violation(plate)
        if isinstance(result, discord.Embed):
            await interaction.followup.send(embed=result)
        else:
            await interaction.followup.send(result)

    @app_commands.command(name="register", description="Đăng ký biển số mới")
    async def register(self, interaction: discord.Interaction, plate: str):
        """Đăng ký biển số mới"""
        user_plates = [p for p, uid in self.bot.data_manager.data.items() 
                      if uid == interaction.user.id]
        
        if len(user_plates) >= MAX_PLATES:
            await interaction.response.send_message(
                f"⚠️ Bạn đã đăng ký tối đa {MAX_PLATES} biển số!",
                ephemeral=True
            )
            return

        plate = re.sub(r'\s+|[^a-zA-Z0-9]', '', plate.strip().upper())
        if not re.match(r'^\d{2}[A-Z]{1,2}\d{5,6}$', plate):
            await interaction.response.send_message(
                "⚠️ Biển số không đúng định dạng!",
                ephemeral=True
            )
            return

        self.bot.data_manager.data[plate] = interaction.user.id
        self.bot.data_manager.save_data()
        
        embed = discord.Embed(
            title="✅ Đăng ký thành công",
            description=f"Đã đăng ký biển số {plate}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list", description="Xem danh sách biển số đã đăng ký")
    async def list_plates(self, interaction: discord.Interaction):
        """Hiển thị danh sách biển số"""
        user_plates = [p for p, uid in self.bot.data_manager.data.items() 
                      if uid == interaction.user.id]
        
        if not user_plates:
            await interaction.response.send_message(
                "❌ Bạn chưa đăng ký biển số nào!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="📋 Danh sách biển số đã đăng ký",
            description=f"Số lượng: {len(user_plates)}/{MAX_PLATES}",
            color=discord.Color.blue()
        )
        
        for plate in user_plates:
            embed.add_field(name="🚗 Biển số", value=plate, inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Xóa biển số đã đăng ký")
    async def remove_plate(self, interaction: discord.Interaction, plate: str):
        """Xóa biển số"""
        plate = re.sub(r'\s+|[^a-zA-Z0-9]', '', plate.strip().upper())
        
        if (plate in self.bot.data_manager.data and 
            self.bot.data_manager.data[plate] == interaction.user.id):
            del self.bot.data_manager.data[plate]
            self.bot.data_manager.save_data()
            
            embed = discord.Embed(
                title="✅ Xóa thành công",
                description=f"Đã xóa biển số {plate}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "❌ Biển số không tồn tại hoặc không thuộc về bạn!",
                ephemeral=True
            )

    @tasks.loop(hours=24)
    async def check_violations(self):
        """Kiểm tra vi phạm tự động (chạy vào thứ 2)"""
        if datetime.datetime.now().weekday() != 0:
            return
        
        print("🔍 Đang kiểm tra vi phạm tự động...")
        for plate, user_id in self.bot.data_manager.data.items():
            try:
                result = await self.check_violation(plate)
                if isinstance(result, discord.Embed):
                    user = self.bot.get_user(user_id)
                    if user:
                        try:
                            await user.send(embed=result)
                        except discord.Forbidden:
                            print(f"Không thể gửi DM cho user {user_id}")
            except Exception as e:
                print(f"Lỗi kiểm tra biển số {plate}: {e}")
            await asyncio.sleep(10)

# Khởi tạo và chạy bot
bot = VehicleBot()
bot.add_cog(VehicleCommands(bot))
bot.run('YOUR_DISCORD_BOT_TOKEN')
