import datetime as dt
from typing import Optional, cast

import discord
from discord import app_commands
from discord.ext import commands

from parrot.bot import Parrot
from parrot.utils import ParrotEmbed
from parrot.utils.exceptions import UserMissingPermissions
from parrot.utils.trace import trace

@trace
class Registration(commands.Cog):
	def __init__(self, bot: Parrot) -> None:
		self.bot = bot

	@app_commands.command(
		name="register",
		description="Register to let Parrot imitate you.",
	)
	@app_commands.guild_only()
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="Member to register (must be yourself)")
	async def register(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.Member] = None,
	) -> None:
		target = who or cast(discord.Member, interaction.user)
		if target.id != interaction.user.id:
			raise UserMissingPermissions("You can only register yourself.")

		self.bot.crud.member.set_registered(target, True)

		embed = ParrotEmbed(
			title="✅ Registered!",
			color=ParrotEmbed.Color.GREEN,
			description=(
				"Now Korbwalker can start learning your speech patterns and "
				"imitate you."
			),
		)
		now = dt.datetime.now()
		if now - DAY_PARROT_UNREGISTERED_EVERYONE > CHANGE_EXPLANATION_PERIOD:
			embed.add_field(
				name="Tip:",
				value=(
					"Try the `/quickstart` command to "
					"immediately give Korbwalker a dataset to imitate you from! It "
					"will scan your past messages to create a model of how you "
					"speak so you can start using Korbwalker right away."
				),
			)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(
		name="unregister",
		description="Remove your registration from Parrot.",
	)
	@app_commands.guild_only()
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="Member to unregister (must be yourself)")
	async def unregister(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.Member] = None,
	) -> None:
		target = who or cast(discord.Member, interaction.user)
		if target.id != interaction.user.id:
			raise UserMissingPermissions("You can only unregister yourself.")

		self.bot.crud.member.set_registered(target, False)

		embed = ParrotEmbed(
			title="Unregistered!",
			color=ParrotEmbed.Color.GRAY,
			description=(
				"Korbwalker will no longer be able to imitate you and it "
				"has stopped collecting your messages.\n\n_If you're done with "
				"Korbwalker and don't want it to have your messages anymore, or if "
				"you just want a fresh start, you can do "
				"`/forget here` or `/forget everywhere` and your existing data "
				"will be permanently deleted from Korbwalker._"
			),
		)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(
		name="status",
		description="Check if you're registered with Parrot.",
	)
	@app_commands.guild_only()
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(who="Member whose registration status to check")
	async def status(
		self,
		interaction: discord.Interaction,
		who: Optional[discord.Member] = None,
	) -> None:
		target = who or cast(discord.Member, interaction.user)
		user_is = (
			"You are"
			if target.id == interaction.user.id
			else f"{target.mention} is"
		)
		if target.bot:
			await interaction.response.send_message(
				"✅ Bots do not need to be registered."
			)
			return
		if self.bot.crud.member.is_registered(target):
			await interaction.response.send_message(
				f"✅ {user_is} currently registered with Korbwalker."
			)
		else:
			await interaction.response.send_message(
				f"❌ {user_is} not currently registered with Korbwalker."
			)

	@app_commands.command(
		name="togglerandomwawa",
		description="Un/block Korbwalker from randomly doing wawa on you.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def toggle_random_wawa(self, interaction: discord.Interaction) -> None:
		wants = self.bot.crud.user.toggle_random_wawa(interaction.user)
		await interaction.response.send_message(
			f"✅ Random wawa {'en' if wants else 'dis'}abled"
		)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Registration(bot))
