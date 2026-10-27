^^^^^^^^^
Changelog
^^^^^^^^^

1.17.0 (2026-10-27)
-------------------
* feat(release): publish builds of main into the edge channel (#36)
* feat(release): hand what the release built to a publisher repository (#34)
* feat(release): open release pull requests with the release GitHub App (#35)
* feat(release): build released packages for every distro after tagging them (#32)
* feat(release): changelog releases for repositories without ROS packages (#30)
* fix(release): take a changelog section for a tagged version as history (#38)

1.16.1 (2026-10-22)
-------------------
* fix(release): name what an override downgrades in the release summary (#31)

1.16.0 (2026-10-21)
-------------------
* feat(release): carry a package's source tarball to the archive (#27)
* feat(release)!: build the .deb for amd64 and arm64 on native runners (#26)

1.15.0 (2026-10-21)
-------------------
* feat(ci)!: evaluate also repos.list of every dependency (#29)
* fix(release): detect packages whose package.xml is at the repository root (#25)

1.14.0 (2026-10-19)
-------------------
* fix(ici): send CI_PAT as an auth header and disable git prompts (#24)
* feat(ici): install every requirements.txt in the repository (#23)

1.13.0 (2026-10-14)
-------------------
* No changes.

1.12.0 (2026-10-14)
-------------------
* fix: title check for new packages with previously empty version (#21)

1.11.0 (2026-10-14)
-------------------
* feat(orchestrator): add extra_distros input (#22)

1.10.0 (2026-10-12)
-------------------
* feat(ci): publish status badges to a badges branch (#20)

1.9.0 (2026-10-05)
------------------
* feat: publish a built package into a signed archive root (#19)

1.8.0 (2026-09-14)
------------------
* fix: make workflows composite actions and expand allowed title types (#18)

1.7.3 (2026-09-10)
------------------
* chore: add gh all workflows that require it (#16)

1.7.2 (2026-09-10)
------------------
* chore: add gh to runner scratch environment (#15)

1.7.1 (2026-09-09)
------------------
* fix: release regex coverage and runner inputs to workflows (#14)

1.7.0 (2026-09-09)
------------------
* feat(release): generate release pull requests, per package or per repo (#13)
* ci: update CI orchestrator workflow to use duatic_devtools (#12)
* ci: add reusable title check workflow (#11)

1.6.1 (2026-09-03)
------------------
* ci: pin the shared pre-commit config to devtools v1 (#10)

1.6.0 (2026-09-03)
------------------
* feat: add release helpers (#9)
* ci: add reusable release check workflow (#8)

1.5.1 (2026-08-26)
------------------
* fix: increase job timeout from 30 to 60 minutes (#7)

1.5.0 (2026-08-25)
------------------
* feat(ci): test with cyclonedds (#6)

1.4.1 (2026-08-05)
------------------
* fix: stop @claude review from cancelling itself (#5)

1.4.0 (2026-08-05)
------------------
* feat: add  @claude review on PRs (#4)

1.3.2 (2026-07-22)
------------------
* feat(ci): run all orchestrator jobs on the configured runner

1.3.1 (2026-07-16)
------------------
* fix: update badges for skipped or cancelled runs

1.3.0 (2026-07-14)
------------------
* feat(ci): add opt-in gist-backed status badges (#3)

1.2.0 (2026-07-04)
------------------
* feat(ci): auto-detect requirements.txt and Aptfile in reusable_ici.yml
* feat(ci): add Release workflow (#2)

1.1.0 (2026-07-03)
------------------
* feat(ci): add orchestrator entry point, centralize matrix and policy

1.0.0 (2026-07-03)
------------------
* feat(ci): add reusable ROS industrial_ci and pre-commit workflows
