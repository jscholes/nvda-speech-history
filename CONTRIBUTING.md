# Speech History Contributions

Contributions to Speech History are welcome, but please ensure that they conform with the following guidelines:

1. With the exception of localisation files, all communication within this repository must take place in English or Spanish.  Names, comments, and documentation within the code must be in English.
2. Before creating an issue:
	* Look through the currently open issues.  If an existing issue matches yours, add to the comments on that issue rather than making a new one.
	* Look through the currently closed issues.  If an existing issue matches yours, you can comment and ask for it to be reopened as long as the relevant behaviour (e.g. a new feature suggestion) hasn't previously been turned down.
3. Before submitting a non-localisation-related pull request (PR):
	* Make an issue clearly describing your enhancement, new feature, bug, etc.
	* For a non-bugfix change, include relevant use cases and reasons why you think it will help users, and wait for the issue to be approved.
	* PRs submitted without a corresponding issue, or before the corresponding issue has been approved, will probably be closed without being merged.
4. Localisation PRs may be submitted without a corresponding issue being created first, as long as they don't make any other unrelated changes.
5. When submitting a PR:
	* Each non-localisation-related PR must correspond to exactly one open issue.  PRs implementing multiple unrelated changes will be closed without being merged.
	* Do not alter the add-on's NVDA compatibility flags in the manifest file, unless that is the only modification being made in the PR.  PRs which change the compatibility flags in addition to other, unrelated changes will be closed without being merged.
	* When applicable, include the text `"Closes #N"` in your PR description, where `#N` is the relevant GitHub issue.
	* Follow all existing code and documentation conventions that have been established so far in the add-on.  Do not perform code cleanup that is not related to or required by the specific changes you're implementing.
	* If you use large language models (LLMs) or other generative artificial intelligence (AI) tools during the creation of your PR, you must:
		* Clearly disclose how they have been used;
		* confirm that you have manually read, reviewed, and tested every generated or modified line of the files changed in your PR;
		* write your own PR description, rather than having the tool(s) generate it for you; and
		* take full responsibility for your contributions as your own work.
		
		PRs may be rejected if the undisclosed use of AI is suspected.  All PRs will be reviewed equally regardless of AI tool involvement.
