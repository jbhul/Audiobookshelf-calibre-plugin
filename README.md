# Audiobookshelf Calibre Plugin

A calibre plugin to synchronize metadata from Audiobookshelf to calibre.

## Features

- Sync metadata from Audiobookshelf to Calibre
- Sync back changes from Calibre to Audiobookshelf
- View reading progress from Audiobookshelf
- Schedule automatic syncs
- Quick link multiple books based on ASIN matching

## Installation

1. Go to your calibre's _Preferences_ > _Plugins_ > _Get new plugins_ and search
   for _Audiobookshelf Sync_
2. Click _Install_
3. Restart calibre

### Manual Installation

1. Download the latest release from the releases page
2. In Calibre, go to Preferences -> Plugins
3. Click "Load plugin from file" and select the downloaded zip file
4. Restart Calibre

## Setup

Pick and choose the metadata you would like to sync and create the
appropriate columns in calibre. The plugin makes this easy, simply select
the **create new columns** option in the config dropdowns.

1. Right click the Audiobookshelf icon and click configure
2. Click "Add Audiobookshelf Account" and enter your Audiobookshelf server details:
   - Server URL (default: <http://localhost:13378>)
   - [API Key](https://www.audiobookshelf.org/guides/api-keys/)
   - Click "Load Libraries" after entering the API key to select audiobook libraries to filter out of manual linking, Quick Link, and the "Not in Calibre" view. Leave all libraries unchecked to include every audiobook library; at least one library must remain unchecked.
   - Optionally set up scheduled sync
3. Configure columns and other settings
4. Link Books and Sync

## Usage

### Sync

Click the Audiobookshelf icon in the toolbar or right-click and select "Sync from Audiobookshelf"

### Available Columns

<details>
<summary><b>See Columns</b></summary>

| Column                       | Description                                                   | Type         |
|------------------------------|---------------------------------------------------------------|--------------|
| Audiobook Title*             | Title of the audiobook                                        | Text         |
| Audiobook Subtitle*          | Subtitle of the audiobook                                     | Text         |
| Audiobook Description*       | Description of the audiobook                                  | Comments     |
| Audiobook Narrator*          | Narrator name(s)                                              | Text (Names) |
| Audiobook Author*            | Author name(s)                                                | Text (Names) |
| Audiobook Chapters           | List of Chapters with Timestamps                              | Comments     |
| Audiobook Series*            | Series of the audiobook                                       | Series       |
| Audiobook Language*          | Language of the audiobook                                     | Text         |
| Audiobook Genres*            | Genres tagged for the audiobook                               | Text (Tags)  |
| Audiobook Tags*              | Tags associated with the audiobook                            | Text (Tags)  |
| Audiobook Publisher*         | Publisher of the audiobook                                    | Text         |
| Audiobook Publish Year*      | Year the audiobook was published                              | Integer      |
| Audiobook Abridged*          | Indicates if the audiobook is abridged                        | Yes/No       |
| Audiobook Explicit*          | Indicates if the audiobook is explicit                        | Yes/No       |
||||
| Audiobook Size               | Size of the audiobook in MB                                   | Integer      |
| Audiobook Duration           | Duration of the audiobook formatted as Hrs:Min                | Text         |
| Audiobook File Count         | Number of files that comprise the audiobook                   | Integer      |
| Audiobook Supplementary Files| Number and list of all Supplementary Files with the audiobook | Text         |
| Audiobook Chapter Count      | Number of chapters in the audiobook                           | Integer      |
||||
| Audiobookshelf Library       | Audiobookshelf Library the audiobook is located in            | Text         |
| Audiobookshelf Date Added    | The date the audiobook was added to Audiobookshelf            | Date         |
| Audiobookshelf Full Path     | Full path to the audiobook                                    | Text         |
| Audiobookshelf Relative Path | Relative Path of the audiobook                                | Text         |
||||
| Audiobook Last Read Date     | The last date the audiobook was read                          | Date         |
| Audiobook Precise Progress   | Progress percentage with decimal precision                    | Float        |
| Audiobook Progress           | Progress percentage as a whole number                         | Integer      |
| Audiobook Progress Time      | How far in the audiobook you are as Hrs:Min                   | Text         |
| Audiobook Time Remaining     | Time remaining in audiobook as Hrs:Min                        | Text         |
| Audiobook Listen Time        | Time listened to the audiobook factoring skips as Hrs:Min     | Text         |
| Audiobook Session Time       | Time spent actually listening factoring speed as Hrs:Min      | Text         |
| Audiobook Time to Finish     | Time to finish audiobook factoring speed as Hrs:Min           | Text         |
||||
| Audiobook Started?           | Indicates if the audiobook has been started                   | Yes/No       |
| Audiobook Begin Date         | The date when the audiobook reading began                     | Date         |
| Audiobook Status             | Status of the audiobook (started/finished)                    | Text         |
||||
| Audiobook Finished?          | Indicates if the audiobook has been finished                  | Yes/No       |
| Audiobook Finish Date        | The date when the audiobook was finished                      | Date         |
| Average Playback Speed       | Average Playback Speed of the Audiobook                       | Float        |
| Max Playback Speed           | Highest Session Playback Speed of the Audiobook               | Float        |
| Number of Reading Sessions   | The # of sessions you listened to the audiobook               | Integer      |
| Average Session Length       | The average time spent listening factoring speed as Hrs:Min   | Text         |
| Number of Days Read          | The # of days you listened to the audiobook                   | Integer      |
| Audiobook Days to Finish     | The time between book start and finish as Days:Hrs:Min        | Text         |
||||
| Audiobook Bookmarks          | Bookmarks in the format 'title at time' (time as hh:mm:ss)    | Comments     |
| Audiobook Collections*       | Collections and Playlists associated with the audiobook       | Text (Tags)  |
||||
| Audible Average Rating       | Average Overall Rating from Audible with Half Stars           | Rating       |
| Audible Average Performance Rating | Average Performance Rating from Audible with Half Stars | Rating       |
| Audible Average Story Rating | Average Story Rating from Audible with Half Stars             | Rating       |
| Audible Rating Count         | Number of (star) ratings on Audible (overall ratings)         | Integer      |
| Audible Review Count         | Number of (text) reviews on Audible                           | Integer      |

</details>

#### Scheduled Sync

Set and Forget!  
Enable scheduled sync in the plugin configuration to automatically sync metadata at a specified time once a day.

### Linking Books

1. Select books in your Calibre library
2. Right-click the Audiobookshelf icon and select "Link Audiobookshelf Book"
3. Select the matching book from your Audiobookshelf library
   Matched titles/authors will be highlighted and shown at the top for easier identification, a reading progress indicator will show which books you've started.

Library filters configured in Audiobookshelf Account Settings are applied to manual linking, Quick Link, and the "Not in Calibre" view. Other Audiobookshelf libraries remain available for metadata synchronization and other features.

#### Quick Link Books

Quick Linking attempts to link books that haven't been linked by matching up Audiobookshelf ASIN (Audible ASIN).  
It searches Audible for a list of Audible ASINs that may match the title and author of the calibre book, and then
checks if any Audiobookshelf book matches. You can review these matches prior to linking.  
By default QuickLink saves a list of calibre books it failed to match (due to no ASIN match) which is more time and API efficient.
You can disable this. You can clear the cache in settings, or individually remove items from the cache when it pops up during Quick Link.

1. Right-click the Audiobookshelf icon and select "Quick Link Books"
2. Books will be automatically matched based on Audible ASIN matches
3. Review the matches and use the checkbox to deselect any you do not want to match
4. Click 'Link Selected' to confirm linking

### Audiobooks Not in Calibre

Builds a table of audiobooks in Audiobookshelf that aren't linked to a book in calibre.  
Double click the title to open the book in Audiobookshelf.

You can check off books in this list to add blank books in calibre with basic metadata and
pre-linked to ABS. You might want to do this to make your calibre library complete and have
a central database of books & audiobooks.

### Additional Settings

Skip syncing books that have already been read in Audiobookshelf.  
Only update books that have been read since last sync.  
Add a button to quickly unlink Audiobooks.  
Set custom strings for started and finished books.

### Audible ASIN Sync

Sync over the Audible ASIN from Audiobookshelf which adds a link to the Audible page straight from calibre.  
This also lets you sync Audible review/rating data directly into calibre. Make sure you select your region
to ensure you have accurate results.

### Audiobookshelf Covers

Directly fetch Audiobookshelf covers and easily update calibre with them. Select the books you want to get
covers for, select the books you want to confirm cover update for, and click "OK" to quickly and easily update calibre covers.

### Writeback

This plugin allows calibre to push metadata back to Audiobookshelf when changed inside of calibre.  
Any of the columns with a * are able to be easily sync'd back to Audiobookshelf.  
This feature is offered with the disclaimer that this will edit your Audiobookshelf database.
Make sure you have Audiobookshelf backups enabled in case this borks anything up, which it shouldn't but you never know.  
The API key provided needs to have permissions to update items for this to work.  
For Collections/Playlists, this plugin will not create new ones, only update existing.

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/jbhul/Audiobookshelf-calibre-plugin/issues).

## Acknowledgements

- The wonderful dev of [Audiobookshelf](https://github.com/advplyr/audiobookshelf)
  for making a wonderful program with an amazing API.
- Some code borrowed from--and heavily inspired by--the
  great [KOReader Sync](https://github.com/harmtemolder/koreader-calibre-plugin)
  calibre plugin.
- Some code borrowed from--and heavily inspired by--the
  great [Goodreads Sync](https://www.mobileread.com/forums/showthread.php?t=123281)
  calibre plugin.
