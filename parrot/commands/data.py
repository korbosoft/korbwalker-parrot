import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from parrot.bot import Parrot
from parrot.utils import (
	ParrotEmbed,
	cast_not_none,
	checks,
	slow,
	tag,
)
from parrot.utils.exceptions import (
	NoData,
	UserMissingPermissions,
)
from parrot.utils.trace import trace
from parrot.utils.types import Snowflake


type UserOrMember = discord.User | discord.Member

type ConfirmationStore = dict[int, Data.Confirmation]


class ForgetConfirmView(discord.ui.View):
	def __init__(
		self,
		cog: "Data",
		*,
		confirmation_key: int,
		confirmation_store: ConfirmationStore,
		done_message: str,
		action: Callable[[UserOrMember], Coroutine[Any, Any, Any]],
		timeout: float = 60.0,
	) -> None:
		super().__init__(timeout=timeout)
		self.cog = cog
		self.confirmation_key = confirmation_key
		self.confirmation_store = confirmation_store
		self.done_message = done_message
		self.action = action
		self.message: discord.Message | None = None

	@discord.ui.button(
		label="Confirm Delete",
		style=discord.ButtonStyle.danger,
	)
	async def confirm_button(
		self,
		interaction: discord.Interaction,
		button: discord.ui.Button["ForgetConfirmView"],
	) -> None:
		confirmation = self.confirmation_store.get(self.confirmation_key)
		if confirmation is None:
			await interaction.response.send_message(
				"This confirmation has expired.",
				ephemeral=True,
			)
			return

		if interaction.user.id != confirmation.requestor.id:
			await interaction.response.send_message(
				"Only the user who requested this action can confirm it.",
				ephemeral=True,
			)
			return

		del self.confirmation_store[self.confirmation_key]
		for item in self.children:
			if isinstance(item, discord.ui.Button):
				item.disabled = True

		await interaction.response.defer()
		user = confirmation.subject_user
		await self.action(user)

		embed = ParrotEmbed(
			title=f"Korbwalker has forgotten {tag(user)}.",
			color=ParrotEmbed.Color.GRAY,
			description=self.done_message,
		)
		if self.message is not None:
			await self.message.edit(embed=embed, view=self)
		await interaction.followup.send(embed=embed, ephemeral=True)
		self.stop()

	@discord.ui.button(
		label="Cancel",
		style=discord.ButtonStyle.secondary,
	)
	async def cancel_button(
		self,
		interaction: discord.Interaction,
		button: discord.ui.Button["ForgetConfirmView"],
	) -> None:
		confirmation = self.confirmation_store.get(self.confirmation_key)
		if confirmation is None:
			await interaction.response.send_message(
				"This confirmation has expired.",
				ephemeral=True,
			)
			return

		if interaction.user.id != confirmation.requestor.id:
			await interaction.response.send_message(
				"Only the user who requested this action can cancel it.",
				ephemeral=True,
			)
			return

		del self.confirmation_store[self.confirmation_key]
		for item in self.children:
			if isinstance(item, discord.ui.Button):
				item.disabled = True

		embed = ParrotEmbed(
			title="Canceled",
			color=ParrotEmbed.Color.GRAY,
			description="Deletion request canceled.",
		)
		if self.message is not None:
			await self.message.edit(embed=embed, view=self)
		await interaction.response.send_message("Canceled.", ephemeral=True)
		self.stop()

	async def on_timeout(self) -> None:
		self.confirmation_store.pop(self.confirmation_key, None)
		for item in self.children:
			if isinstance(item, discord.ui.Button):
				item.disabled = True
		if self.message is not None:
			embed = ParrotEmbed(
				title="Are you sure?",
				color=ParrotEmbed.Color.ORANGE,
				description="Request expired.",
			)
			try:
				await self.message.edit(embed=embed, view=self)
			except discord.HTTPException:
				pass


@trace
class Data(commands.Cog):
	@dataclass
	class Confirmation:
		requestor: UserOrMember
		subject_user: UserOrMember

	def __init__(self, bot: Parrot) -> None:
		self.bot = bot
		self.pending_full_confirmations: ConfirmationStore = {}
		self.pending_guild_confirmations: ConfirmationStore = {}
		self._next_confirmation_id = 0

	def _allocate_confirmation_id(self) -> int:
		self._next_confirmation_id += 1
		return self._next_confirmation_id

	@app_commands.command(
		name="download",
		description="Request a copy of your data.",
	)
	@app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id, i.user.id))
	async def download(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		temp_path = Path("temp.json")
		with temp_path.open("w+", encoding="utf-8") as f:
			ujson.dump(self.bot.crud.user.get_raw(interaction.user), f)

		await interaction.followup.send(
			"I don't want to rely on automatically using a file hosting service so you'll have to ask me (@korbosoft) to send it over",
			ephemeral=True,
		)

	@app_commands.command(
		name="avatar",
		description="Show your antiavatar or another member's antiavatar.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="Member whose antiavatar to show")
	async def avatar(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.Member] = None,
	) -> None:
		target = who or cast(discord.Member, interaction.user)
		avatar_location = await self.bot.antiavatars.fetch(target)
		if avatar_location.startswith(("http://", "https://")):
			await interaction.response.send_message(avatar_location)
		else:
			path = Path(avatar_location)
			await interaction.response.send_message(
				file=discord.File(path, filename=path.name)
			)

	async def _start_forget(
		self,
		interaction: discord.Interaction,
		*,
		who: UserOrMember | None,
		confirmation_store: ConfirmationStore,
		are_you_sure_message_fmt: str,
		done_message: str,
		action: Callable[[UserOrMember], Coroutine[Any, Any, Any]],
	) -> None:
		target: UserOrMember = who or interaction.user

		if (
			target.id != interaction.user.id
			and not checks.is_admin(interaction)
			and not target.bot
		):
			raise UserMissingPermissions(
				"You are not allowed to make Korbwalker forget other users."
			)

		if not self.bot.crud.user.exists(target):
			raise NoData.User(target)

		confirm_id = self._allocate_confirmation_id()
		confirmation_store[confirm_id] = Data.Confirmation(
			requestor=interaction.user,
			subject_user=target,
		)

		embed = ParrotEmbed(
			title="Are you sure?",
			color=ParrotEmbed.Color.ORANGE,
			description=are_you_sure_message_fmt.format(who=target.mention),
		).set_footer(text="Action will be automatically canceled in 1 minute.")

		view = ForgetConfirmView(
			self,
			confirmation_key=confirm_id,
			confirmation_store=confirmation_store,
			done_message=done_message,
			action=action,
			timeout=60.0,
		)

		await interaction.response.send_message(embed=embed, view=view)
		view.message = await interaction.original_response()

	forget_group = app_commands.Group(
		name="forget",
		description="Delete data that Parrot has collected.",
	)

	@forget_group.command(
		name="everywhere",
		description="Delete ALL your data from Parrot.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="User whose data to delete (defaults to yourself)")
	async def forget_everywhere(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.User] = None,
	) -> None:
		are_you_sure_message_fmt = (
			"This will permanently delete the data of {who} from Korbwalker."
		)
		done_message = (
			"All of the data that Korbwalker has collected from this "
			"user has been deleted."
		)
		await self._start_forget(
			interaction,
			who=who,
			confirmation_store=self.pending_full_confirmations,
			are_you_sure_message_fmt=are_you_sure_message_fmt,
			done_message=done_message,
			action=self.bot.crud.user.delete_all_data,
		)

	@forget_group.command(
		name="here",
		description="Delete your messages in this server.",
	)
	@app_commands.guild_only()
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="Member whose server data to delete")
	async def forget_here(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.Member] = None,
	) -> None:
		guild = cast_not_none(interaction.guild)
		are_you_sure_message_fmt = (
			"This will permanently delete the messages collected from {who} "
			f"in server {guild.name}."
		)
		done_message = (
			"All of the messages that Korbwalker has collected from this "
			"user in this server have been deleted."
		)
		member_leave_guild = cast(
			Callable[[UserOrMember], Coroutine[Any, Any, bool]],
			self.bot.crud.member.leave_guild,
		)
		await self._start_forget(
			interaction,
			who=who,
			confirmation_store=self.pending_guild_confirmations,
			are_you_sure_message_fmt=are_you_sure_message_fmt,
			done_message=done_message,
			action=member_leave_guild,
		)

	@app_commands.command(
		name="size",
		description="How many messages are in your corpus in this server?",
	)
	@app_commands.guild_only()
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="Member whose server corpus size to check")
	@slow
	async def size(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.Member] = None,
	) -> None:
		target = who or cast(discord.Member, interaction.user)
		corpus_size = await self.bot.crud.member.size(target)
		whose = (
			"your" if target.id == interaction.user.id else f"{target.mention}'s"
		)
		await interaction.response.send_message(
			f"{corpus_size:,} messages in {whose} corpus on this server"
		)

	@app_commands.command(
		name="globalsize",
		description="How many messages are in your corpus across Discord?",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@slow
	async def globalsize(self, interaction: discord.Interaction) -> None:
		corpus_size = await self.bot.crud.user.size(interaction.user)
		await interaction.response.send_message(
			f"{corpus_size:,} messages in your corpus across Discord"
		)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Data(bot))
