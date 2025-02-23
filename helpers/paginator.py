from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, Optional

import nextcord
from nextcord.ext import commands
from nextcord.ext import menus

class GroupHelpPageSource(menus.ListPageSource):
    def __init__(self, group, cog_commands, *, prefix, total_commands, usable_commands):
        super().__init__(entries=cog_commands, per_page=15)
        self.group = group
        self.prefix = prefix
        self.total_commands = total_commands
        self.usable_commands = usable_commands

        if isinstance(group, nextcord.ext.commands.Group):
            self.title = f"Help - {self.group.name}"
            self.description = f"{(self.group.help or 'No help given...').replace('%PRE%', self.prefix)}"
        else:
            self.title = f"Help - {self.group.qualified_name}"
            self.description = f"{self.group.description}"

    def get_minimal_command_signature(self, command):
        if isinstance(command, commands.Group):
            return '[G] %s%s %s' % (self.prefix, command.qualified_name, command.signature)
        return '(c) %s%s %s' % (self.prefix, command.qualified_name, command.signature)

    async def format_page(self, menu, cog_commands):

        colors = [0x910023, 0xA523FF]
        color = random.choice(colors)

        command_signatures = [self.get_minimal_command_signature(c) for c in cog_commands]
        val = "\n".join(command_signatures)

        if isinstance(self.group, nextcord.ext.commands.Group):
            text = f"""
{self.description}
            """

        else:
            text = f"""
{getattr(self.group, 'COG_EMOJI', None)} {self.group.__doc__}
            """

        embed = nextcord.Embed(title=self.title, description=f"""
Total commands: {self.total_commands}
Commands usable by you (in this server): {self.usable_commands}
                              """, timestamp=nextcord.utils.utcnow(), color=color)
        embed.add_field(name=f"__**Available Commands ({self.total_commands})**__", value=f"""
{text}
```yaml
{val}
```
[G] means group, these have sub-commands.
(C) means command, these do not have sub-commands.
                        """)
        embed.set_footer(text="<> = required argument | [] = optional argument\nDo NOT type these when using commands!")

        maximum = self.get_max_pages()

        if maximum > 1:
            embed.set_author(name=f'Page {menu.current_page + 1}/{maximum} ({len(self.entries)} commands)')

        return embed

class ViewPaginator(nextcord.ui.View):
    def __init__(
            self,
            source: menus.PageSource,
            *,
            ctx: commands.Context,
            check_embeds: bool = True,
            compact: bool = False,
    ):
        super().__init__()
        self.source: menus.PageSource = source
        self.check_embeds: bool = check_embeds
        self.ctx: commands.Context = ctx
        self.message: Optional[nextcord.Message] = None
        self.current_page: int = 0
        self.compact: bool = compact
        self.input_lock = asyncio.Lock()
        self.clear_items()
        self.fill_items()

    def fill_items(self) -> None:
        if not self.compact:
            self.numbered_page.row = 1
            self.stop_pages.row = 1

        if self.source.is_paginating():
            max_pages = self.source.get_max_pages()
            use_last_and_first = max_pages is not None and max_pages >= 2
            if use_last_and_first:
                self.add_item(self.go_to_first_page)  # type: ignore
            self.add_item(self.go_to_previous_page)  # type: ignore
            if not self.compact:
                self.add_item(self.go_to_current_page)  # type: ignore
            self.add_item(self.go_to_next_page)  # type: ignore
            if use_last_and_first:
                self.add_item(self.go_to_last_page)  # type: ignore
            if not self.compact:
                self.add_item(self.numbered_page)  # type: ignore
            self.add_item(self.stop_pages)  # type: ignore

    async def _get_kwargs_from_page(self, page: int) -> Dict[str, Any]:
        value = await nextcord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {'content': value, 'embed': None}
        elif isinstance(value, nextcord.Embed):
            return {'embed': value, 'content': None}
        else:
            return {}

    async def show_page(self, interaction: nextcord.Interaction, page_number: int) -> None:
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(page_number)
        if kwargs:
            if interaction.response.is_done():
                if self.message:
                    await self.message.edit(**kwargs, view=self)
            else:
                await interaction.response.edit_message(**kwargs, view=self)

    def _update_labels(self, page_number: int) -> None:
        self.go_to_first_page.disabled = page_number == 0
        if self.compact:
            max_pages = self.source.get_max_pages()
            self.go_to_last_page.disabled = max_pages is None or (page_number + 1) >= max_pages
            self.go_to_next_page.disabled = max_pages is not None and (page_number + 1) >= max_pages
            self.go_to_previous_page.disabled = page_number == 0
            return

        self.go_to_current_page.label = str(page_number + 1)
        self.go_to_previous_page.label = str(page_number)
        self.go_to_next_page.label = str(page_number + 2)
        self.go_to_next_page.disabled = False
        self.go_to_previous_page.disabled = False
        self.go_to_first_page.disabled = False

        max_pages = self.source.get_max_pages()
        if max_pages is not None:
            self.go_to_last_page.disabled = (page_number + 1) >= max_pages
            if (page_number + 1) >= max_pages:
                self.go_to_next_page.disabled = True
                self.go_to_next_page.label = '…'
            if page_number == 0:
                self.go_to_previous_page.disabled = True
                self.go_to_previous_page.label = '…'

    async def show_checked_page(self, interaction: nextcord.Interaction, page_number: int) -> None:
        max_pages = self.source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(interaction, page_number)
            elif max_pages > page_number >= 0:
                await self.show_page(interaction, page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: nextcord.Interaction) -> bool:
        if interaction.user and interaction.user.id in (self.ctx.bot.owner_id, self.ctx.author.id):
            return True
        await interaction.response.send_message('This pagination menu cannot be controlled by you, sorry!',
                                                ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.message:
            await self.message.edit(view=None)

    async def on_error(self, error: Exception, item: nextcord.ui.Item, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            await interaction.followup.send('An unknown error occurred, sorry', ephemeral=True)
        else:
            await interaction.response.send_message('An unknown error occurred, sorry', ephemeral=True)

    async def start(self) -> None:
        if self.check_embeds and not self.ctx.channel.permissions_for(self.ctx.me).embed_links:
            await self.ctx.send('Bot does not have embed links permission in this channel.')
            return

        await self.source._prepare_once()
        page = await self.source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(0)
        self.message = await self.ctx.send(**kwargs, view=self)

    @nextcord.ui.button(emoji="<:first:921408035597983745>", style=nextcord.ButtonStyle.grey)
    async def go_to_first_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """go to the first page"""
        await self.show_page(interaction, 0)

    @nextcord.ui.button(emoji="<:previous:921408043470688267>", style=nextcord.ButtonStyle.grey)
    async def go_to_previous_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """go to the previous page"""
        await self.show_checked_page(interaction, self.current_page - 1)

    @nextcord.ui.button(label="Current", style=nextcord.ButtonStyle.grey, disabled=True)
    async def go_to_current_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        pass

    @nextcord.ui.button(emoji="<:next:921408056766636073>", style=nextcord.ButtonStyle.grey)
    async def go_to_next_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """go to the next page"""
        await self.show_checked_page(interaction, self.current_page + 1)

    @nextcord.ui.button(emoji="<:last:921408062886146088>", style=nextcord.ButtonStyle.grey)
    async def go_to_last_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(interaction, self.source.get_max_pages() - 1)

    @nextcord.ui.button(label="Skip to page...", style=nextcord.ButtonStyle.grey)
    async def numbered_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """lets you type a page number to go to"""
        if self.input_lock.locked():
            await interaction.response.send_message('Already waiting for your response...', ephemeral=True)
            return

        if self.message is None:
            return

        async with self.input_lock:
            channel = self.message.channel
            author_id = interaction.user and interaction.user.id
            await interaction.response.send_message('What page do you want to go to?', ephemeral=True)

            def message_check(m):
                return m.author.id == author_id and channel == m.channel and m.content.isdigit()

            try:
                msg = await self.ctx.bot.wait_for('message', check=message_check, timeout=30.0)
            except asyncio.TimeoutError:
                await interaction.followup.send('Took too long.', ephemeral=True)
                await asyncio.sleep(5)
            else:
                page = int(msg.content)
                await msg.delete()
                await self.show_checked_page(interaction, page - 1)

    @nextcord.ui.button(emoji="<:close:921408051091759114>", style=nextcord.ButtonStyle.red)
    async def stop_pages(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """stops the pagination session."""
        await interaction.response.defer()
        await interaction.delete_original_message()
        self.stop()