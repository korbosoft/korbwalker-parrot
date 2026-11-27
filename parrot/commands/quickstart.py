import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, cast

import asyncio_atexit
import discord
from discord import app_commands
from discord.ext import commands

from parrot.bot import Parrot
from parrot.utils import (
	HistoryCrawler,
	ParrotEmbed,
	checks,
	is_learnable,
)
from parrot.utils.exceptions import (
	AlreadyScanning,
	UserMissingPermissions,
	WrongChannelType,
)
from parrot.utils.trace import trace
from parrot.utils.types import Snowflake


class CancelReason(Enum):
	USER = auto()
	SYSTEM = auto()


@dataclass
class Scan:
	member_id: Snowflake
	guild_id: Snowflake
	status_message: discord.Message
	status_fmt: str
	dm_embed: discord.Embed
	crawler: HistoryCrawler
	cancel_reason: CancelReason | None = None


type OngoingScans = dict[Snowflake, Scan]


def _check_admin(interaction: discord.Interaction) -> bool:
	return checks.is_admin(interaction)


@trace
class Quickstart(commands.Cog):
	def __init__(self, bot: Parrot) -> None:
		self.bot = bot
		self.ongoing_scans: OngoingScans = {}
		asyncio_atexit.register(self._cancel_all, loop=self.bot.loop)

	@commands.Cog.listener()
	async def on_raw_reaction_add(
		self,
		payload: discord.RawReactionActionEvent,
	) -> None:
		if payload.emoji.name != "❌":
			return
		scan_id = payload.message_id
		if scan_id not in self.ongoing_scans:
			return
		self._cancel_scan(scan_id, CancelReason.USER)

	@staticmethod
	async def _live_update_status(scan: Scan) -> None:
		while scan.crawler.running:
			scan.dm_embed.description = scan.status_fmt.format(
				num_collected=scan.crawler.num_collected
			)
			await scan.status_message.edit(embed=scan.dm_embed)
			await asyncio.sleep(2)

	@app_commands.command(
		name="quickstart",
		description="Scrape your past messages in this server to get started using Parrot right away.",
	)
	@app_commands.guild_only()
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(user="Optional user to scan (admins only, for bots)")
	async def quickstart(
		self,
		interaction: discord.Interaction,
		user: Optional[discord.User] = None,
	) -> None:
		guild = interaction.guild
		if not is_learnable(interaction.channel) or guild is None:
			raise WrongChannelType("Quickstart is only available in servers.")

		target_user: discord.User | discord.Member = user or interaction.user
		if isinstance(target_user, discord.User) and not isinstance(
			target_user, discord.Member
		):
			fetched_member = guild.get_member(target_user.id)
			if fetched_member is not None:
				target_user = fetched_member

		if target_user.id == interaction.user.id:
			member = cast(discord.Member, interaction.user)
		else:
			if not _check_admin(interaction):
				raise UserMissingPermissions(
					"You can only run Quickstart on yourself."
				)
			if not target_user.bot:
				raise UserMissingPermissions(
					"Quickstart can only be run on behalf of bots."
				)
			member = (
				target_user
				if isinstance(target_user, discord.Member)
				else await guild.fetch_member(target_user.id)
			)

		self.bot.crud.member.assert_registered(member)

		for scan in self.ongoing_scans.values():
			if scan.member_id == member.id and scan.guild_id == member.guild.id:
				name = (
					"you" if interaction.user.id == member.id else member.mention
				)
				raise AlreadyScanning(
					f"❌ Quickstart is already running for {name} in this "
					"server!"
				)

		await interaction.response.defer(ephemeral=True, thinking=True)

		scan_id: Snowflake | None = None
		try:
			status_fmt = (
				f"**Scanning in _{member.guild.name}_...**\n"
				"Collected {num_collected} new messages..."
			)
			dm_embed = ParrotEmbed(
				description=status_fmt.format(num_collected=0)
			)
			dm_embed.set_author(name="Quickstart")
			dm_embed.set_footer(
				text=f"Scanning for {member.mention}",
				icon_url=member.display_avatar.url,
			)
			status_message = await interaction.user.send(embed=dm_embed)
			scan_id = status_message.id

			await status_message.add_reaction("❌")

			whose = (
				"your"
				if interaction.user.id == member.id
				else f"{member.mention}'s"
			)
			chat_embed = ParrotEmbed(
				title="Quickstart is scanning",
				description=(
					"Korbwalker is now scanning this server and learning from "
					f"{whose} past messages.\nThis could take a few minutes."
					"\nCheck your DMs to see its progress."
				),
			)
			await interaction.followup.send(embed=chat_embed, ephemeral=True)

			histories: list[AsyncIterator[discord.Message]] = []
			learning_channel_ids = self.bot.crud.guild.get_learning_channel_ids(
				guild
			)
			for channel_id in learning_channel_ids:
				channel = await self.bot.fetch_channel(channel_id)
				if not is_learnable(channel):
					continue
				try:
					channel_member = await channel.guild.fetch_member(
						member.id
					)
				except discord.errors.NotFound:
					continue
				histories.append(
					channel.history(
						limit=100_000,
						after=channel_member.joined_at,
					)
				)

			def crawler_action(message: discord.Message) -> bool:
				result = self.bot.crud.message.record_or_update(message)
				return result == self.bot.crud.message.CreateOrUpdate.CREATED

			crawler = HistoryCrawler(
				histories=histories,
				action=crawler_action,
				filter=lambda message: message.author.id == member.id,
				limit=100_000,
			)

			scan = Scan(
				member_id=member.id,
				guild_id=member.guild.id,
				status_message=status_message,
				status_fmt=status_fmt,
				dm_embed=dm_embed,
				crawler=crawler,
			)
			self.ongoing_scans[scan_id] = scan
			async with asyncio.TaskGroup() as tg:
				tg.create_task(Quickstart._live_update_status(scan))
				tg.create_task(crawler.crawl())

			dm_embed = ParrotEmbed()
			if interaction.user.id == member.id:
				name = "you"
			else:
				name = f"{member.mention}"
				dm_embed.set_footer(
					text=(
						f"Scanning for {member.display_name} in "
						f"_{member.guild.name}_"
					),
					icon_url=member.display_avatar.url,
				)
			if scan.cancel_reason is not None:
				dm_embed.description = (
					"**Scan cancelled.**\n"
					f"Collected {crawler.num_collected} new messages."
				)
				if scan.cancel_reason == CancelReason.SYSTEM:
					dm_embed.description += (
						"\nCancelled by system: Korbwalker is restarting"
					)
				dm_embed.set_author(name="🛑 Quickstart")
			else:
				dm_embed.description = (
					"**Scan complete.**\n"
					f"Collected {crawler.num_collected} new messages."
				)
				dm_embed.set_author(name="✅ Quickstart")
			if crawler.num_collected == 0:
				dm_embed.description += (
					f"\n😕 Couldn't find any messages from {name}."
				)
				dm_embed.color = ParrotEmbed.Color.RED.value
			if scan.cancel_reason is not None:
				dm_embed.color = ParrotEmbed.Color.GRAY.value

			async with asyncio.TaskGroup() as tg:
				tg.create_task(status_message.delete())
				tg.create_task(interaction.user.send(embed=dm_embed))
			del self.ongoing_scans[status_message.id]
		except Exception:
			if scan_id is not None and scan_id in self.ongoing_scans:
				del self.ongoing_scans[scan_id]
			raise

	def _cancel_scan(self, scan_id: Snowflake, reason: CancelReason) -> None:
		scan = self.ongoing_scans[scan_id]
		scan.cancel_reason = reason
		scan.crawler.stop()

	def _cancel_all(self) -> None:
		for scan_id in self.ongoing_scans:
			self._cancel_scan(scan_id, CancelReason.SYSTEM)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Quickstart(bot))
