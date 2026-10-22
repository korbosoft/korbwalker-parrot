from discord.ext import commands

from parrot.bot import Parrot
from parrot.utils import ParrotEmbed, cast_not_none, tag
from parrot.utils.trace import trace


@trace
class Miscellaneous(commands.Cog):
	def __init__(self, bot: Parrot):
		self.bot = bot

	@commands.command()
	@commands.cooldown(2, 4, commands.BucketType.user)
	async def ping(self, ctx: commands.Context) -> None:
		"""Get the bot's reponse time."""
		await ctx.reply(
			f"NEED PING??? Took **{round(self.bot.latency * 1000, 2)}** ms"
		)

	@commands.command(
		aliases=["about", "bio", "code", "github", "source", "sourcecode"]
	)
	@commands.cooldown(2, 4, commands.BucketType.user)
	async def info(self, ctx: commands.Context) -> None:
		"""Get info about Parrot."""
		korbosoft = await self.bot.fetch_user(206235904644349953)

		bio = (
			f"Korbwalker can imitate everyone. "
			f"Do `{self.bot.command_prefix}imitate me` to have Parrot imitate "
			f"you, or do `{self.bot.command_prefix}help` to see what else "
			"Parrot can do."
		)

		embed = ParrotEmbed(
			title="Korbwalker",
			description=bio,
		)
		embed.add_field(
			name="GitHub",
			value="https://github.com/korbosoft/korbwalker-parrot",
		)
		embed.set_thumbnail(url=cast_not_none(self.bot.user).display_avatar.url)
		embed.set_footer(
			text=f"Korbwalker v4 • Made by {tag(korbosoft)}",
			icon_url=korbosoft.display_avatar.url,
		)

		await ctx.reply(embed=embed)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Miscellaneous(bot))
